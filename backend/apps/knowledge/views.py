"""Curriculum library API: upload, index, search.

Who may write here is deliberately narrow. A national document is visible to
every school on the platform, so only a platform superuser may create one; a
school admin may add their own school's documents and nothing else.
"""

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.media import SignedFileField
from apps.common.uploads import validate_document
from apps.schools.moe import structure_summary

from .ingest import extract_text, index_document
from .models import Chunk, Document, Source
from .retrieval import authority_spread, search, visible_documents


def _require_admin(user):
    if not (user.is_superuser or user.role == "ADMIN"):
        raise PermissionDenied("Only the school admin can change the curriculum library.")


class SourceSerializer(serializers.ModelSerializer):
    authority_label = serializers.CharField(source="get_authority_display", read_only=True)
    rank = serializers.IntegerField(read_only=True)

    class Meta:
        model = Source
        fields = "__all__"


def _require_platform(user):
    """The Source table is global — one MoE authority weighting shared by every
    tenant's retrieval and AI-generated schemes. Only the platform operator (a
    school-less superuser) may change it; a single school admin must not be able
    to demote or delete a source every other school depends on."""
    if not (user.is_superuser and getattr(user, "school_id", None) is None):
        raise PermissionDenied("The shared curriculum sources are managed by the platform operator.")


class SourceViewSet(viewsets.ModelViewSet):
    queryset = Source.objects.all()
    serializer_class = SourceSerializer
    filterset_fields = ["authority"]
    search_fields = ["name", "publisher"]

    def perform_create(self, serializer):
        _require_platform(self.request.user)
        serializer.save()

    def perform_update(self, serializer):
        _require_platform(self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        _require_platform(self.request.user)
        instance.delete()


class DocumentSerializer(serializers.ModelSerializer):
    file = SignedFileField(required=False, allow_null=True, validators=[validate_document])
    source_name = serializers.CharField(source="source.name", read_only=True)
    authority = serializers.CharField(source="source.authority", read_only=True)
    authority_label = serializers.CharField(
        source="source.get_authority_display", read_only=True
    )
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    learning_area_name = serializers.CharField(
        source="learning_area.name", read_only=True, default=None
    )
    national = serializers.BooleanField(source="is_national", read_only=True)
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = "__all__"
        # `school` stays writable: a platform superuser publishes a national
        # document by sending it as null. DocumentViewSet._scope decides who may.
        read_only_fields = ["uploaded_by", "indexed_at"]

    def get_chunk_count(self, obj):
        return obj.chunks.count()


class DocumentViewSet(viewsets.ModelViewSet):
    """National documents plus this school's own — never another tenant's."""

    serializer_class = DocumentSerializer
    filterset_fields = ["kind", "learning_area", "source"]
    search_fields = ["title"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return visible_documents(self.request.user.school).prefetch_related("chunks")

    def _scope(self, serializer):
        """Where this document belongs, and whether the caller may put it there.

        A school admin may only ever write to their own school. Publishing a
        national document reaches every tenant on the platform, so it is
        reserved for a platform superuser.
        """
        user = self.request.user
        requested = serializer.validated_data.pop("school", "unset")

        if user.is_superuser:
            return None if requested is None else (
                user.school if requested == "unset" else requested
            )

        if requested is None:
            raise PermissionDenied(
                "A national document is visible to every school — only a platform "
                "administrator can publish one. Save it as a school document instead."
            )
        if requested != "unset" and requested != user.school:
            raise PermissionDenied("You can only add documents to your own school.")
        return user.school

    def perform_create(self, serializer):
        _require_admin(self.request.user)
        school = self._scope(serializer)
        document = serializer.save(school=school, uploaded_by=self.request.user)
        if not document.text and document.file:
            document.text = extract_text(document.file)
            if document.text:
                document.save(update_fields=["text", "updated_at"])
        if document.text:
            index_document(document)

    def perform_update(self, serializer):
        _require_admin(self.request.user)
        document = serializer.save()
        if document.text:
            index_document(document)

    def perform_destroy(self, instance):
        _require_admin(self.request.user)
        if instance.is_national and not self.request.user.is_superuser:
            raise PermissionDenied("National documents are managed by the platform.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def reindex(self, request, pk=None):
        _require_admin(request.user)
        document = self.get_object()
        if not document.text:
            return Response(
                {"detail": "This document has no text to index. Paste or re-upload it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        count = index_document(document)
        return Response({"chunks": count, "indexed_at": document.indexed_at})

    @action(detail=True)
    def chunks(self, request, pk=None):
        document = self.get_object()
        return Response(
            [
                {
                    "id": c.id,
                    "ordinal": c.ordinal,
                    "heading": c.heading,
                    "text": c.text,
                }
                for c in Chunk.objects.filter(document=document)
            ]
        )


class CurriculumSearchView(APIView):
    """GET /api/curriculum/search/?q=&learning_area=&grade=

    Returns cited passages ordered with authority weighting, plus which
    authorities answered and which one governs if they disagree.
    """

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"detail": "Pass ?q= to search."}, status=400)

        learning_area = request.query_params.get("learning_area") or None
        grade = request.query_params.get("grade")
        try:
            grade = int(grade) if grade not in (None, "") else None
        except ValueError:
            return Response({"detail": "grade must be a number."}, status=400)
        try:
            learning_area = int(learning_area) if learning_area else None
        except ValueError:
            return Response({"detail": "learning_area must be an id."}, status=400)

        passages = search(
            query,
            school=request.user.school,
            learning_area=learning_area,
            grade=grade,
            limit=int(request.query_params.get("limit", 8)),
        )
        return Response(
            {
                "query": query,
                "results": [p.to_dict() for p in passages],
                "authority": authority_spread(passages),
            }
        )


class MoeStructureView(APIView):
    """GET /api/moe/structure/ — the canon that settles conflicts."""

    def get(self, request):
        return Response(structure_summary())
