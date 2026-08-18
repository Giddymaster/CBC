from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.parent_login import CreateParentLoginView, LoginView
from apps.accounts.password_reset import (
    PasswordResetConfirmView,
    PasswordResetOptionsView,
    PasswordResetRequestView,
    VerificationPeekView,
)
from apps.accounts.passwords import AdminResetPasswordView, ChangePasswordView
from apps.accounts.verify_views import (
    MyContactView,
    MyVerifyConfirmView,
    MyVerifyRequestView,
    TwoFactorView,
    VerifyLinkConfirmView,
)
from apps.accounts.views import MeView
from apps.assessments.broadsheet import (
    BroadsheetView,
    BroadsheetXlsxView,
    ClassReportPdfView,
)
from apps.assessments.subject_analysis import SubjectAnalysisView
from apps.assessments.views import (
    AssessmentViewSet,
    GenerateClassReportCardsView,
    LearningAreaViewSet,
    ReportCardPdfView,
    ReportCardView,
    ScoreBulkView,
    ScoreViewSet,
)
from apps.attendance.views import (
    AttendanceBulkView,
    AttendanceMonthView,
    AttendanceViewSet,
)
from apps.common.audit_views import AuditEntryViewSet, AuditSummaryView
from apps.common.media import serve_media
from apps.communication.parent_messages import (
    LearnerContactsView,
    ParentMessageViewSet,
    ParentThreadsView,
    StaffThreadsView,
)
from apps.communication.views import (
    AnnouncementViewSet,
    MessageBlastViewSet,
    MessagingStatusView,
    SmsMessageViewSet,
)
from apps.facilities.views import (
    FacilityAssignmentViewSet,
    FacilityBulkImportView,
    FacilityCategoryViewSet,
    FacilityViewSet,
    NavSectionViewSet,
    SupplyViewSet,
)
from apps.interop.views import kemis_enrollment, kemis_learners_csv
from apps.knowledge.views import (
    CurriculumSearchView,
    DocumentViewSet,
    LearningResourceViewSet,
    MoeStructureView,
    SourceViewSet,
)
from apps.payments.views import (
    C2BConfirmationView,
    FeeRegisterXlsxView,
    FeeStructureGridView,
    FeeStructureViewSet,
    GenerateInvoicesView,
    InvoiceViewSet,
    PaymentViewSet,
    StkCallbackView,
    StkPushView,
)

# Aliased on import: several names (InvoiceViewSet, AnnouncementViewSet, PlanViewSet)
# also exist in the tenant apps, and the DRF router keys on class name.
from apps.platform.views import (
    AnnouncementViewSet as PlatformAnnouncementViewSet,
)
from apps.platform.views import (
    InvoiceViewSet as PlatformInvoiceViewSet,
)
from apps.platform.views import (
    MySchoolSubscriptionView,
    OperatorAdminMemberView,
    OperatorAdminResetView,
    OperatorOverviewView,
    OperatorSchoolAdminView,
    OperatorSchoolView,
    PlatformAnnouncementFeedView,
    ProvisionView,
    SubscriptionViewSet,
)
from apps.platform.views import (
    PlanViewSet as PlatformPlanViewSet,
)
from apps.promotions.views import (
    AcademicYearViewSet,
    PromotionOutcomeViewSet,
    PromotionRunViewSet,
    TransitionInfoView,
)
from apps.schools.locations import LocationsView
from apps.schools.profile import MySchoolProfileView, SchoolDocumentViewSet
from apps.schools.structure import (
    GradeDetailView,
    GradeStreamsView,
    SchoolStructureView,
)
from apps.schools.views import SchoolViewSet
from apps.students.admissions import (
    AdmissionRightViewSet,
    AdmissionView,
    BulkImportView,
    LearnerPhotoView,
    MyAdmissionAccessView,
)
from apps.students.portal import ParentSummaryView
from apps.students.views import (
    ClassGroupViewSet,
    GuardianViewSet,
    LearnerFieldViewSet,
    LearnerViewSet,
    PathwayViewSet,
)
from apps.teachers.daily import (
    SchemeLessonPlansView,
    StaffRollCallHistoryView,
    StaffRollCallView,
)
from apps.teachers.development import (
    PdRecordViewSet,
    PeerReviewQueueView,
    PeerReviewViewSet,
    SchoolAnalysisView,
    TeacherAnalysisView,
)
from apps.teachers.my_portal import (
    DutyCatalogView,
    DutyViewSet,
    MyPhotoView,
    MyPortalView,
    StaffReportViewSet,
)
from apps.teachers.notifications import NotificationsView
from apps.teachers.portal import TeacherSummaryView
from apps.teachers.staff import (
    AddTeacherView,
    EditTeacherView,
    StaffBulkImportView,
    StaffDirectoryView,
    StaffFieldViewSet,
    SupportStaffViewSet,
)
from apps.teachers.team import (
    MyTeamView,
    StaffMessageViewSet,
    StaffTaskViewSet,
    TeamMemberView,
)
from apps.teachers.views import LessonPlanViewSet, SchemeOfWorkViewSet, TeacherViewSet
from apps.timetable.views import (
    AutoAssignView,
    GenerateTimetableView,
    LessonRequirementViewSet,
    LessonViewSet,
    PeriodViewSet,
    RoomViewSet,
)

router = DefaultRouter()
router.register("schools", SchoolViewSet)
router.register("audit", AuditEntryViewSet, basename="audit")
router.register("platform/plans", PlatformPlanViewSet, basename="platform-plan")
router.register("platform/subscriptions", SubscriptionViewSet, basename="subscription")
router.register(
    "platform/invoices", PlatformInvoiceViewSet, basename="platform-invoice"
)
router.register(
    "platform/announcements", PlatformAnnouncementViewSet, basename="platform-announcement"
)
router.register("pathways", PathwayViewSet)
router.register("learners", LearnerViewSet)
router.register("guardians", GuardianViewSet)
router.register("class-groups", ClassGroupViewSet)
router.register("learner-fields", LearnerFieldViewSet)
router.register("admission-rights", AdmissionRightViewSet)
router.register("academic-years", AcademicYearViewSet)
router.register("promotions/runs", PromotionRunViewSet)
router.register("promotions/outcomes", PromotionOutcomeViewSet)
router.register("curriculum/sources", SourceViewSet)
router.register("curriculum/documents", DocumentViewSet, basename="document")
router.register("learning-resources", LearningResourceViewSet, basename="learning-resource")
router.register("nav-sections", NavSectionViewSet)
router.register("facility-categories", FacilityCategoryViewSet)
router.register("facilities", FacilityViewSet)
router.register("facility-assignments", FacilityAssignmentViewSet)
router.register("supplies", SupplyViewSet)
router.register("teachers", TeacherViewSet)
router.register("support-staff", SupportStaffViewSet)
router.register("staff-reports", StaffReportViewSet)
router.register("duties", DutyViewSet)
router.register("staff-tasks", StaffTaskViewSet)
router.register("staff-messages", StaffMessageViewSet)
router.register("staff-fields", StaffFieldViewSet)
router.register("pd-records", PdRecordViewSet)
router.register("peer-reviews", PeerReviewViewSet, basename="peerreview")
router.register("schemes-of-work", SchemeOfWorkViewSet)
router.register("lesson-plans", LessonPlanViewSet)
router.register("learning-areas", LearningAreaViewSet)
router.register("assessments", AssessmentViewSet)
router.register("scores", ScoreViewSet)
router.register("attendance", AttendanceViewSet)
router.register("timetable/rooms", RoomViewSet)
router.register("timetable/periods", PeriodViewSet)
router.register("timetable/lessons", LessonViewSet)
router.register("timetable/requirements", LessonRequirementViewSet)
router.register("communication/sms", SmsMessageViewSet)
router.register("communication/announcements", AnnouncementViewSet)
router.register("communication/parent-messages", ParentMessageViewSet)
router.register("communication/blasts", MessageBlastViewSet)
router.register("school-documents", SchoolDocumentViewSet)
router.register("payments/fee-structures", FeeStructureViewSet)
router.register("payments/invoices", InvoiceViewSet)
router.register("payments/payments", PaymentViewSet)

urlpatterns = [
    # Django's own admin lives off the beaten path: /admin belongs to the
    # school's SPA, and the default location is the first door every scanner
    # rattles.
    path("django-admin/", admin.site.urls),
    path("api/auth/token/", LoginView.as_view()),
    path("api/parent-logins/", CreateParentLoginView.as_view()),
    path("api/me/", MeView.as_view()),
    path("api/me/password/", ChangePasswordView.as_view()),
    path("api/password-reset/options/", PasswordResetOptionsView.as_view()),
    path("api/password-reset/request/", PasswordResetRequestView.as_view()),
    path("api/password-reset/confirm/", PasswordResetConfirmView.as_view()),
    path("api/me/contact/", MyContactView.as_view()),
    path("api/me/verify/request/", MyVerifyRequestView.as_view()),
    path("api/me/verify/confirm/", MyVerifyConfirmView.as_view()),
    path("api/me/2fa/", TwoFactorView.as_view()),
    path("api/verify/confirm-link/", VerifyLinkConfirmView.as_view()),
    path("api/verify/<str:token>/", VerificationPeekView.as_view()),
    path(
        "api/school/staff/<int:user_id>/reset-password/",
        AdminResetPasswordView.as_view(),
    ),
    path("api/audit/summary/", AuditSummaryView.as_view()),
    path("api/platform/provision/", ProvisionView.as_view()),
    path("api/platform/overview/", OperatorOverviewView.as_view()),
    path("api/platform/schools/<int:pk>/", OperatorSchoolView.as_view()),
    path("api/platform/schools/<int:pk>/admin/", OperatorSchoolAdminView.as_view()),
    path(
        "api/platform/schools/<int:pk>/admin/<int:uid>/",
        OperatorAdminMemberView.as_view(),
    ),
    path(
        "api/platform/schools/<int:pk>/admin/<int:uid>/reset-password/",
        OperatorAdminResetView.as_view(),
    ),
    path("api/my-school/subscription/", MySchoolSubscriptionView.as_view()),
    path("api/platform-announcements/", PlatformAnnouncementFeedView.as_view()),
    path("api/communication/status/", MessagingStatusView.as_view()),
    path("api/my-school/profile/", MySchoolProfileView.as_view()),
    path("api/locations/", LocationsView.as_view()),
    path("api/school/structure/", SchoolStructureView.as_view()),
    path("api/school/streams/", GradeStreamsView.as_view()),
    path("api/school/staff/", StaffDirectoryView.as_view()),
    path("api/school/analysis/", SchoolAnalysisView.as_view()),
    path("api/school/subject-analysis/", SubjectAnalysisView.as_view()),
    path("api/duties/catalog/", DutyCatalogView.as_view()),
    path("api/staff/roll-call/", StaffRollCallView.as_view()),
    path("api/staff/roll-call/history/", StaffRollCallHistoryView.as_view()),
    path(
        "api/schemes-of-work/<int:scheme_id>/lesson-plans/",
        SchemeLessonPlansView.as_view(),
    ),
    path("api/teachers/<int:teacher_id>/analysis/", TeacherAnalysisView.as_view()),
    path("api/peer-review/queue/", PeerReviewQueueView.as_view()),
    path("api/school/staff/add-teacher/", AddTeacherView.as_view()),
    path("api/school/staff/bulk/", StaffBulkImportView.as_view()),
    path("api/facilities/bulk/", FacilityBulkImportView.as_view()),
    path("api/school/staff/teachers/<int:teacher_id>/", EditTeacherView.as_view()),
    path("api/school/grades/<grade>/", GradeDetailView.as_view()),
    path("api/admissions/", AdmissionView.as_view()),
    path("api/admissions/access/", MyAdmissionAccessView.as_view()),
    path("api/admissions/bulk/", BulkImportView.as_view()),
    path("api/learners/<int:learner_id>/photo/", LearnerPhotoView.as_view()),
    path("api/notifications/", NotificationsView.as_view()),
    path("api/curriculum/search/", CurriculumSearchView.as_view()),
    path("api/moe/structure/", MoeStructureView.as_view()),
    path("api/promotions/transitions/", TransitionInfoView.as_view()),
    path("api/parent/summary/", ParentSummaryView.as_view()),
    path("api/parent/threads/", ParentThreadsView.as_view()),
    path("api/staff/parent-threads/", StaffThreadsView.as_view()),
    path("api/learners/<int:learner_id>/contacts/", LearnerContactsView.as_view()),
    path("api/teacher/summary/", TeacherSummaryView.as_view()),
    path("api/my-portal/", MyPortalView.as_view()),
    path("api/my-portal/photo/", MyPhotoView.as_view()),
    path("api/my-team/", MyTeamView.as_view()),
    path("api/my-team/<int:user_id>/", TeamMemberView.as_view()),
    path("api/attendance/bulk/", AttendanceBulkView.as_view()),
    path("api/attendance/month/", AttendanceMonthView.as_view()),
    path("api/scores/bulk/", ScoreBulkView.as_view()),
    path("api/report-card/<int:learner_id>/", ReportCardView.as_view()),
    path("api/report-card/<int:learner_id>/pdf/", ReportCardPdfView.as_view()),
    path("api/report-cards/generate-class/", GenerateClassReportCardsView.as_view()),
    path("api/report-cards/broadsheet/", BroadsheetView.as_view()),
    path("api/report-cards/broadsheet.xlsx", BroadsheetXlsxView.as_view()),
    path("api/report-cards/class.pdf", ClassReportPdfView.as_view()),
    path("api/timetable/generate/", GenerateTimetableView.as_view()),
    path("api/timetable/assignments/auto/", AutoAssignView.as_view()),
    path("api/payments/fee-structures/grid/", FeeStructureGridView.as_view()),
    path("api/payments/generate-invoices/", GenerateInvoicesView.as_view()),
    path("api/payments/register.xlsx", FeeRegisterXlsxView.as_view()),
    path("api/payments/stk-push/", StkPushView.as_view()),
    # The webhook secret rides in the path Safaricom calls; see _webhook_authentic.
    path("api/payments/stk-callback/<str:secret>/", StkCallbackView.as_view()),
    path("api/payments/c2b-confirmation/<str:secret>/", C2BConfirmationView.as_view()),
    path("api/interop/kemis/learners.csv", kemis_learners_csv),
    path("api/interop/kemis/enrollment/", kemis_enrollment),
    path("api/", include(router.urls)),
    # Uploaded files, gated by signed link — same path in dev and production,
    # so a missing signature shows up on a laptop, not on a parent's phone.
    path("media/<path:path>", serve_media),
]
