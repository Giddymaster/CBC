from django.contrib import admin

from .models import (
    LessonPlan,
    ProfessionalDevelopmentRecord,
    SchemeOfWork,
    Teacher,
    TeacherAttendance,
)

admin.site.register(Teacher)
admin.site.register(SchemeOfWork)
admin.site.register(LessonPlan)
admin.site.register(ProfessionalDevelopmentRecord)
admin.site.register(TeacherAttendance)
