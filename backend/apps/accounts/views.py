from rest_framework.response import Response
from rest_framework.views import APIView


class MeView(APIView):
    """Who am I — the frontend uses this to pick staff vs parent UI."""

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "full_name": user.get_full_name(),
                "role": user.role,
                "school": user.school.name if user.school else None,
                "is_guardian": hasattr(user, "guardian_profile"),
            }
        )
