"""Who may speak in the school's name.

A blast goes out under the school's sender ID and costs the school money per
message, so the door is narrow: the office, the head teacher and the deputy —
the people who already sign notices — and the bursar, whose fee reminders are
the most common notice of all. A class teacher talks to their parents on the
learner thread, not with a school-wide megaphone.
"""

from apps.payments.access import is_bursar, is_office, is_school_leadership


def can_send_blast(user):
    return is_office(user) or is_school_leadership(user) or is_bursar(user)
