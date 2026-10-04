from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Grant superuser/admin access to an existing user.'

    default_username = 'ahmed_medhat'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            nargs='?',
            default=self.default_username,
            help='Username to promote (defaults to ahmed_medhat).',
        )
        parser.add_argument(
            '--staff-only',
            action='store_true',
            help='Grant admin site access without superuser rights.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']

        user = User.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f'No user found with username "{username}".')

        user.is_staff = True
        if not options['staff_only']:
            user.is_superuser = True
        user.save(update_fields=['is_staff', 'is_superuser'])

        role = 'superuser' if user.is_superuser else 'staff'
        self.stdout.write(self.style.SUCCESS(f'"{username}" is now a {role}.'))