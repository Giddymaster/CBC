from django.contrib import admin

from .models import Announcement, SmsMessage

admin.site.register(SmsMessage)
admin.site.register(Announcement)
