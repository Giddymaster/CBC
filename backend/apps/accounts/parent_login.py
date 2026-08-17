"""Parents sign in with their child's number.

A parent remembers the admission number on the fee slip and the UPI on the
report form. They do not remember a username the school invented for them. So
the token endpoint accepts either: a real username, or a child's admission
number or UPI, which resolves to that child's guardian account.

The password still does the protecting. Admission numbers run in sequence and
are printed on every receipt, so they identify — they never authenticate.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.throttling import ScopedRateThrottle

User = get_user_model()


def resolve_login(identifier):
    """Map what was typed to a real username, if it is a child's number.

    Returns the identifier unchanged when it is not one — an unknown value
    then fails authentication normally, which keeps the "invalid credentials"
    answer identical whether or not the number exists.
    """
    from apps.students.models import Learner

    text = (identifier or "").strip()
    if not text:
        return identifier
    # A real account wins — returned in its stored casing, since Django
    # authenticates on an exact username and parents type on phone keyboards.
    account = User.objects.filter(username__iexact=text).first()
    if account is not None:
        return account.username

    learner = (
        Learner.objects.filter(admission_number__iexact=text).first()
        or Learner.objects.filter(upi__iexact=text).first()
    )
    if learner is None:
        return identifier

    guardian = (
        learner.guardians.filter(user__isnull=False, is_primary_contact=True).first()
        or learner.guardians.filter(user__isnull=False).first()
    )
    return guardian.user.username if guardian else identifier


class ParentFriendlyAuthTokenSerializer(AuthTokenSerializer):
    def validate(self, attrs):
        attrs["username"] = resolve_login(attrs.get("username"))
        return super().validate(attrs)


class LoginView(ObtainAuthToken):
    """POST /api/auth/token/ — username, or a child's admission number / UPI."""

    serializer_class = ParentFriendlyAuthTokenSerializer
    # The one door worth brute-forcing. The rate is per client IP and generous
    # enough for a shared staffroom computer, hopeless for a password list.
    throttle_scope = "login"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        # Tell the client who it just signed in as, so a parent who typed an
        # admission number sees whose account they are on.
        token_key = response.data.get("token")
        if token_key:
            from rest_framework.authtoken.models import Token

            user = Token.objects.select_related("user").get(key=token_key).user
            response.data["username"] = user.username
            response.data["name"] = user.get_full_name() or user.username
            response.data["role"] = user.role
            response.data["must_change_password"] = user.must_change_password
        return response


class ParentAccountSerializer(serializers.Serializer):
    learner = serializers.IntegerField()
    guardian = serializers.IntegerField(required=False)


class CreateParentLoginView(ObtainAuthToken):
    """POST /api/parent-logins/ {learner} — give a family portal access.

    The username is the child's admission number, because that is the one
    thing every parent already has written down. The password is generated
    and shown once; the parent must replace it at first sign-in.
    """

    def post(self, request, *args, **kwargs):
        import secrets

        from rest_framework.exceptions import PermissionDenied, ValidationError
        from rest_framework.response import Response

        from apps.students.models import Guardian, Learner

        user = request.user
        if not (user.is_superuser or user.role == "ADMIN"):
            raise PermissionDenied("Only the school office creates parent logins.")

        params = ParentAccountSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        learner = Learner.objects.filter(
            school=user.school, pk=params.validated_data["learner"]
        ).first()
        if learner is None:
            raise ValidationError({"learner": "No such learner at this school."})

        guardians = learner.guardians.all()
        if params.validated_data.get("guardian"):
            guardian = guardians.filter(
                pk=params.validated_data["guardian"]
            ).first()
        else:
            guardian = (
                guardians.filter(is_primary_contact=True).first() or guardians.first()
            )
        if guardian is None:
            raise ValidationError(
                {"learner": "This learner has no guardian on record to give access to."}
            )
        if guardian.user_id:
            return Response({
                "username": guardian.user.username,
                "guardian": guardian.full_name,
                "detail": "This family already has a login.",
                "created": False,
            })

        username = learner.admission_number.strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            username = f"{username}-{secrets.token_hex(2)}"
        password = secrets.token_urlsafe(6)
        account = User.objects.create_user(
            username=username,
            password=password,
            first_name=guardian.full_name.split(" ")[0],
            last_name=" ".join(guardian.full_name.split(" ")[1:]),
            role="PARENT",
            school=user.school,
            phone=guardian.phone,
            email=guardian.email or "",
        )
        account.must_change_password = True
        account.save(update_fields=["must_change_password"])
        Guardian.objects.filter(pk=guardian.pk).update(user=account)

        return Response({
            "username": username,
            "generated_password": password,
            "guardian": guardian.full_name,
            "learner": learner.full_name,
            "created": True,
            "detail": (
                "Hand these over now — the password is not shown again. The "
                "parent signs in with the admission number and chooses their "
                "own password."
            ),
        }, status=201)
