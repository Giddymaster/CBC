from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from apps.accounts.views import MeView
from apps.assessments.views import (
    AssessmentViewSet,
    GenerateClassReportCardsView,
    LearningAreaViewSet,
    ReportCardPdfView,
    ReportCardView,
    ScoreBulkView,
    ScoreViewSet,
)
from apps.attendance.views import AttendanceBulkView, AttendanceViewSet
from apps.communication.views import AnnouncementViewSet, SmsMessageViewSet
from apps.facilities.views import (
    FacilityAssignmentViewSet,
    FacilityCategoryViewSet,
    FacilityViewSet,
    NavSectionViewSet,
    SupplyViewSet,
)
from apps.interop.views import kemis_enrollment, kemis_learners_csv
from apps.knowledge.views import (
    CurriculumSearchView,
    DocumentViewSet,
    MoeStructureView,
    SourceViewSet,
)
from apps.payments.views import (
    C2BConfirmationView,
    FeeStructureViewSet,
    InvoiceViewSet,
    StkCallbackView,
    StkPushView,
)
from apps.promotions.views import (
    AcademicYearViewSet,
    PromotionOutcomeViewSet,
    PromotionRunViewSet,
    TransitionInfoView,
)
from apps.schools.structure import GradeDetailView, SchoolStructureView
from apps.schools.views import SchoolViewSet
from apps.students.admissions import (
    AdmissionRightViewSet,
    AdmissionView,
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
from apps.teachers.my_portal import (
    DutyViewSet,
    MyPhotoView,
    MyPortalView,
    StaffReportViewSet,
)
from apps.teachers.notifications import NotificationsView
from apps.teachers.portal import TeacherSummaryView
from apps.teachers.team import (
    MyTeamView,
    StaffMessageViewSet,
    StaffTaskViewSet,
    TeamMemberView,
)
from apps.teachers.staff import (
    AddTeacherView,
    EditTeacherView,
    StaffDirectoryView,
    StaffFieldViewSet,
    SupportStaffViewSet,
)
from apps.teachers.views import LessonPlanViewSet, SchemeOfWorkViewSet, TeacherViewSet
from apps.timetable.views import (
    GenerateTimetableView,
    LessonRequirementViewSet,
    LessonViewSet,
    PeriodViewSet,
    RoomViewSet,
)

router = DefaultRouter()
router.register("schools", SchoolViewSet)
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
router.register("payments/fee-structures", FeeStructureViewSet)
router.register("payments/invoices", InvoiceViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/token/", obtain_auth_token),
    path("api/me/", MeView.as_view()),
    path("api/school/structure/", SchoolStructureView.as_view()),
    path("api/school/staff/", StaffDirectoryView.as_view()),
    path("api/school/staff/add-teacher/", AddTeacherView.as_view()),
    path("api/school/staff/teachers/<int:teacher_id>/", EditTeacherView.as_view()),
    path("api/school/grades/<grade>/", GradeDetailView.as_view()),
    path("api/admissions/", AdmissionView.as_view()),
    path("api/admissions/access/", MyAdmissionAccessView.as_view()),
    path("api/learners/<int:learner_id>/photo/", LearnerPhotoView.as_view()),
    path("api/notifications/", NotificationsView.as_view()),
    path("api/curriculum/search/", CurriculumSearchView.as_view()),
    path("api/moe/structure/", MoeStructureView.as_view()),
    path("api/promotions/transitions/", TransitionInfoView.as_view()),
    path("api/parent/summary/", ParentSummaryView.as_view()),
    path("api/teacher/summary/", TeacherSummaryView.as_view()),
    path("api/my-portal/", MyPortalView.as_view()),
    path("api/my-portal/photo/", MyPhotoView.as_view()),
    path("api/my-team/", MyTeamView.as_view()),
    path("api/my-team/<int:user_id>/", TeamMemberView.as_view()),
    path("api/attendance/bulk/", AttendanceBulkView.as_view()),
    path("api/scores/bulk/", ScoreBulkView.as_view()),
    path("api/report-card/<int:learner_id>/", ReportCardView.as_view()),
    path("api/report-card/<int:learner_id>/pdf/", ReportCardPdfView.as_view()),
    path("api/report-cards/generate-class/", GenerateClassReportCardsView.as_view()),
    path("api/timetable/generate/", GenerateTimetableView.as_view()),
    path("api/payments/stk-push/", StkPushView.as_view()),
    path("api/payments/stk-callback/", StkCallbackView.as_view()),
    path("api/payments/c2b-confirmation/", C2BConfirmationView.as_view()),
    path("api/interop/kemis/learners.csv", kemis_learners_csv),
    path("api/interop/kemis/enrollment/", kemis_enrollment),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
