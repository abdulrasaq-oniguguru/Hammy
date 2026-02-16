from django.db import models
from django.contrib.auth.models import User
import pyotp


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='auth_profile')
    otp_secret = models.CharField(max_length=32, blank=True, null=True)
    two_factor_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def generate_otp_secret(self):
        """Generate a new OTP secret for the user"""
        self.otp_secret = pyotp.random_base32()
        self.save()
        return self.otp_secret

    def get_totp_uri(self):
        """Get the provisioning URI for QR code generation"""
        if not self.otp_secret:
            self.generate_otp_secret()
        return pyotp.totp.TOTP(self.otp_secret).provisioning_uri(
            name=self.user.email or self.user.username,
            issuer_name='OEM Reporting API'
        )

    def verify_otp(self, otp_code):
        """Verify the provided OTP code"""
        if not self.otp_secret:
            return False
        totp = pyotp.TOTP(self.otp_secret)
        return totp.verify(otp_code, valid_window=1)
