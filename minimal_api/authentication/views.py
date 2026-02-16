from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from .models import UserProfile
import qrcode
import io
import base64


def is_superuser(user):
    """Check if user is a superuser"""
    return user.is_superuser


def login(request):
    """User login view with 2FA support"""
    if request.user.is_authenticated:
        return redirect('oem_reporting:reports_menu')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            profile, created = UserProfile.objects.get_or_create(user=user)

            if profile.two_factor_enabled:
                # Store user_id in session for 2FA verification
                request.session['2fa_user_id'] = user.id
                return redirect('authentication:verify_2fa')
            else:
                # Login directly without 2FA
                auth_login(request, user)
                messages.success(request, f'Welcome back, {user.username}!')
                return redirect('oem_reporting:reports_menu')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'authentication/login.html')


def verify_2fa(request):
    """Verify 2FA code and complete login"""
    user_id = request.session.get('2fa_user_id')

    if not user_id:
        messages.error(request, 'Invalid session. Please login again.')
        return redirect('authentication:login')

    if request.method == 'POST':
        otp_code = request.POST.get('otp_code')

        try:
            user = User.objects.get(id=user_id)
            profile = user.auth_profile

            if profile.verify_otp(otp_code):
                # Clear 2FA session data
                del request.session['2fa_user_id']
                # Login the user
                auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, f'Welcome back, {user.username}!')
                return redirect('oem_reporting:reports_menu')
            else:
                messages.error(request, 'Invalid 2FA code. Please try again.')
        except User.DoesNotExist:
            messages.error(request, 'Invalid user.')
            return redirect('authentication:login')

    return render(request, 'authentication/verify_2fa.html')


@login_required
@user_passes_test(is_superuser)
def setup_2fa(request):
    """Generate QR code for 2FA setup (superuser only)"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Generate new secret
        if not profile.otp_secret or request.POST.get('regenerate'):
            profile.generate_otp_secret()

        totp_uri = profile.get_totp_uri()

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

        return render(request, 'authentication/manage_2fa.html', {
            'qr_code': qr_code_base64,
            'secret': profile.otp_secret,
            'two_factor_enabled': profile.two_factor_enabled
        })

    return render(request, 'authentication/manage_2fa.html', {
        'two_factor_enabled': profile.two_factor_enabled
    })


@login_required
@user_passes_test(is_superuser)
def enable_2fa(request):
    """Enable 2FA after verification (superuser only)"""
    if request.method == 'POST':
        otp_code = request.POST.get('otp_code')

        if not otp_code:
            messages.error(request, 'OTP code is required.')
            return redirect('authentication:setup_2fa')

        profile = request.user.auth_profile

        if profile.verify_otp(otp_code):
            profile.two_factor_enabled = True
            profile.save()
            messages.success(request, '2FA enabled successfully! Your account is now more secure.')
            return redirect('authentication:setup_2fa')
        else:
            messages.error(request, 'Invalid 2FA code. Please try again.')
            return redirect('authentication:setup_2fa')

    return redirect('authentication:setup_2fa')


@login_required
@user_passes_test(is_superuser)
def disable_2fa(request):
    """Disable 2FA for the user (superuser only)"""
    if request.method == 'POST':
        otp_code = request.POST.get('otp_code')

        if not otp_code:
            messages.error(request, 'OTP code is required for verification.')
            return redirect('authentication:setup_2fa')

        profile = request.user.auth_profile

        # Verify OTP before disabling
        if profile.verify_otp(otp_code):
            profile.two_factor_enabled = False
            profile.save()
            messages.success(request, '2FA disabled successfully.')
            return redirect('authentication:setup_2fa')
        else:
            messages.error(request, 'Invalid 2FA code. Please try again.')
            return redirect('authentication:setup_2fa')

    return redirect('authentication:setup_2fa')


@login_required
def check_2fa_status(request):
    """Display 2FA status and management page"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    return render(request, 'authentication/manage_2fa.html', {
        'two_factor_enabled': profile.two_factor_enabled
    })


def logout(request):
    """Logout the user"""
    auth_logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('authentication:login')
