import base64

from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class Command(BaseCommand):
    help = 'Print a fresh VAPID key pair for Web Push (set them as environment variables).'

    def handle(self, *args, **options):
        vapid = Vapid()
        vapid.generate_keys()
        private = vapid.private_key.private_numbers().private_value.to_bytes(32, 'big')
        public = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.stdout.write(f'VAPID_PUBLIC_KEY={_b64(public)}')
        self.stdout.write(f'VAPID_PRIVATE_KEY={_b64(private)}')
        self.stdout.write('CRON_SECRET=<any long random string>')
