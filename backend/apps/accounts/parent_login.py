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


def resolve_login(identifier, school_code=None):
    """Map what was typed to a real username, if it is a child's number.

    A school code scopes the lookup, and it matters: admission numbers are only
    unique *within* a school, so once the platform holds many schools, two of
    them can share "ADM0126". Without the code the query would resolve to
    whichever school's learner it found first — the wrong family, and a silent
    lockout for the other. With the code it is one indexed lookup against
    (school, admission_number), which is both correct and fast.

    Returns the identifier unchanged when it resolves to nothing — an unknown
    value then fails authentication normally, so "invalid credentials" reads the
    same whether or not the number exists.
    """
    from apps.schools.models import School
    from apps.students.models import Learner

    text = (identifier or "").strip()
    if not text:
        return identifier

    def guardian_username(learner):
        guardian = (
            learner.guardians.filter(user__isnull=False, is_primary_contact=True).first()
            or learner.guardians.filter(user__isnull=False).first()
        )
        return guardian.user.username if guardian else None

    if school_code:
        school = School.objects.filter(code__iexact=school_code.strip()).first()
        if school is None:
            # A code was given but names no school — nothing can resolve under
            # it, so fail closed rather than silently searching every tenant.
            return identifier
        # Inside a named school, a child's number is tried FIRST — that is what a
        # parent types — so it cannot be shadowed by a same-looking username in
        # another school. Then a staff username within this school.
        learner = (
            Learner.objects.filter(school=school, admission_number__iexact=text).first()
            or Learner.objects.filter(school=school, upi__iexact=text).first()
        )
        if learner is not None:
            resolved = guardian_username(learner)
            if resolved:
                return resolved
        account = User.objects.filter(username__iexact=text, school=school).first()
        return account.username if account is not None else identifier

    # No code given: a real username wins (staff/admin usernames are globally
    # unique), then a global admission/UPI fallback for a parent who typed no
    # code. This path is ambiguous across schools, which is exactly why the code
    # exists — the form requires it for parents.
    account = User.objects.filter(username__iexact=text).first()
    if account is not None:
        return account.username
    learner = (
        Learner.objects.filter(admission_number__iexact=text).first()
        or Learner.objects.filter(upi__iexact=text).first()
    )
    return guardian_username(learner) or identifier if learner else identifier


def self_service_parent(school_code, admission, upi):
    """Sign a parent in from the report form, with no login pre-created.

    A school cannot hand-make nine hundred parent accounts, so the parent makes
    their own: the three things printed on the child's report form — the school
    code, the admission number and the UPI — stand in for a first credential.
    When they match a real learner, the guardian's account is created (or found)
    with the UPI as its password and a forced change, and a token is issued.

    Possession of the report form is the authorisation here, and the password
    change on first sign-in closes the window — the UPI stops working the moment
    the parent chooses their own. Returns the User, or None when nothing matches
    (an unknown value must fail exactly like a wrong password).
    """
    import secrets

    from apps.schools.models import School
    from apps.students.models import Guardian, Learner

    code = (school_code or "").strip()
    admission = (admission or "").strip()
    upi = (upi or "").strip()
    if not (code and admission and upi):
        return None

    school = School.objects.filter(code__iexact=code).first()
    if school is None:
        return None
    learner = Learner.objects.filter(
        school=school, admission_number__iexact=admission
    ).first()
    if learner is None:
        return None
    # The UPI is the key. A learner with no UPI cannot be self-claimed this way.
    if not learner.upi or learner.upi.strip().lower() != upi.lower():
        return None

    guardian = (
        learner.guardians.filter(is_primary_contact=True).first()
        or learner.guardians.first()
    )
    if guardian is None:
        return None
    if guardian.user_id:
        # The account exists and normal auth already failed — the parent has
        # set their own password and this is not it. The UPI must not reopen it.
        return None

    username = learner.admission_number.strip().lower()
    if User.objects.filter(username__iexact=username).exists():
        username = f"{username}-{secrets.token_hex(2)}"
    parts = guardian.full_name.split(" ")
    user = User.objects.create_user(
        username=username,
        password=learner.upi.strip(),
        first_name=parts[0],
        last_name=" ".join(parts[1:]),
        role="PARENT",
        school=school,
        phone=guardian.phone,
        email=guardian.email or "",
    )
    user.must_change_password = True
    user.save(update_fields=["must_change_password"])
    Guardian.objects.filter(pk=guardian.pk).update(user=user)

    # New account, unproven contacts: start verification for whichever the
    # guardian record carries, so the verified flags (and later 2FA) can mean
    # something. Best-effort — signing in must not fail on a notice.
    from apps.accounts.verify_views import start_contact_verification

    start_contact_verification(user, school=school)
    return user


class ParentFriendlyAuthTokenSerializer(AuthTokenSerializer):
    def validate(self, attrs):
        request = self.context.get("request")
        school_code = ""
        if request is not None:
            school_code = (request.data.get("school_code") or "").strip()

        raw_identifier = attrs.get("username")
        attrs["username"] = resolve_login(raw_identifier, school_code)
        try:
            data = super().validate(attrs)
        except serializers.ValidationError:
            # No account matched — try self-service, where the report form's
            # admission number + UPI + school code create the login on the spot.
            user = self_service_parent(
                school_code, raw_identifier, attrs.get("password")
            )
            if user is None:
                raise
            return {**attrs, "user": user}

        # When a code is given, the account must actually belong to that school.
        # This is what makes the system sure which tenant a login is for — a
        # right password on the wrong school code is still refused. A blank code
        # (operators, or a staff username that is already globally unique) skips
        # the check.
        #
        # The refusal is WORD-FOR-WORD the same as a wrong password. A distinct
        # "wrong school code" message would be an oracle: it only appears after
        # the password verified, so an attacker could confirm stolen passwords
        # by trying them under any code and reading which error came back.
        if school_code:
            user = data["user"]
            school = getattr(user, "school", None)
            if school is None or (school.code or "").lower() != school_code.lower():
                raise serializers.ValidationError(
                    {"non_field_errors": ["Unable to log in with provided credentials."]},
                    code="authorization",
                )
        return data


class LoginView(ObtainAuthToken):
    """POST /api/auth/token/ — username, or a child's admission number / UPI."""

    serializer_class = ParentFriendlyAuthTokenSerializer
    # The one door worth brute-forcing. The rate is per client IP and generous
    # enough for a shared staffroom computer, hopeless for a password list.
    throttle_scope = "login"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request, *args, **kwargs):
        from rest_framework.authtoken.models import Token
        from rest_framework.response import Response

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # Two-factor: a correct password buys a one-time code, not a token.
        # The token is issued only once that code comes back.
        if user.two_factor_enabled:
            from apps.accounts.models import Verification
            from apps.accounts.verification import (
                VerifyResult,
                confirm_code,
                request_verification,
            )
            from apps.accounts.verify_views import latest_login_code, mask

            code = (request.data.get("code") or "").strip()
            if not code:
                # Prefer the phone (codes read faster off SMS); fall back to email.
                if user.phone and user.phone_verified:
                    channel, target = Verification.Channel.SMS, user.phone
                elif user.email:
                    channel, target = Verification.Channel.EMAIL, user.email
                else:
                    channel, target = Verification.Channel.SMS, user.phone
                request_verification(
                    channel=channel,
                    purpose=Verification.Purpose.LOGIN_2FA,
                    target=target,
                    user=user,
                    school=user.school,
                )
                return Response({
                    "two_factor_required": True,
                    "channel": channel,
                    "target": mask(target),
                    "detail": "Enter the code we just sent to finish signing in.",
                })
            if confirm_code(latest_login_code(user), code) != VerifyResult.OK:
                return Response(
                    {"detail": "That code is wrong or has expired."}, status=400
                )

        token, _ = Token.objects.get_or_create(user=user)
        # Tell the client who it just signed in as, so a parent who typed an
        # admission number sees whose account they are on.
        return Response({
            "token": token.key,
            "username": user.username,
            "name": user.get_full_name() or user.username,
            "role": user.role,
            "must_change_password": user.must_change_password,
        })


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

        admission = learner.admission_number.strip()
        username = admission.lower()
        if User.objects.filter(username__iexact=username).exists():
            username = f"{username}-{secrets.token_hex(2)}"
        # Two things the parent already has off the report form, so the office
        # hands over nothing and nobody has to guess: the admission number is the
        # username, the UPI is the first password. Where a learner has no UPI yet
        # the admission number stands in for both. Either way it is a one-time
        # key — must_change_password forces the parent onto the change-password
        # screen first (enforced in the app and by PasswordChangeEnforced).
        upi = (learner.upi or "").strip()
        password = upi or admission
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

        from apps.accounts.verify_views import start_contact_verification

        start_contact_verification(account, school=user.school)

        return Response({
            "username": username,
            "generated_password": password,
            "guardian": guardian.full_name,
            "learner": learner.full_name,
            "created": True,
            "detail": (
                "The parent signs in with the admission number as the username "
                f"and the {'UPI' if upi else 'admission number'} as the password, "
                "then sets their own password on the first screen."
            ),
        }, status=201)
