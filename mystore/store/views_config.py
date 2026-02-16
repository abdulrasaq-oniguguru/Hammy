"""
Store Configuration Management Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import StoreConfiguration, LoyaltyConfiguration, PaymentMethodConfiguration, TaxConfiguration
from django.forms import ModelForm
from django import forms
from decimal import Decimal


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser or (hasattr(u, 'profile') and u.profile.access_level in ['md', 'admin']), login_url='access_denied')
def configuration_menu(request):
    """Main configuration menu page"""
    return render(request, 'config/configuration_menu.html')


def is_admin_or_md(user):
    """Check if user is admin or MD"""
    if user.is_superuser:
        return True
    try:
        return user.profile.access_level in ['md', 'admin']
    except:
        return False


class StoreConfigurationForm(ModelForm):
    """Form for store configuration"""

    class Meta:
        model = StoreConfiguration
        fields = [
            # Store Identity
            'store_name', 'tagline', 'deployment_name',
            # Contact Information
            'email', 'phone', 'phone_2',
            # Address
            'address_line_1', 'address_line_2', 'city', 'state', 'country', 'postal_code',
            # Business Info
            'tax_id', 'website', 'business_hours',
            # Branding
            'logo', 'receipt_logo', 'favicon',
            # Currency & Localization
            'currency_symbol', 'currency_code', 'timezone', 'date_format',
            # Receipt Settings
            'receipt_header_text', 'receipt_footer_text', 'show_receipt_tax_id',
            # Social Media
            'facebook_url', 'instagram_url', 'twitter_url',
            # System
            'is_active'
        ]
        widgets = {
            'store_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Your Store Name'}),
            'tagline': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Quality Products Since 2020'}),
            'deployment_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Main Store, Branch 1'}),

            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1234567890'}),
            'phone_2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Secondary phone (optional)'}),

            'address_line_1': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line_2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),

            'tax_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Business registration number'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://yourwebsite.com'}),
            'business_hours': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g., Mon-Fri: 9AM-6PM, Sat: 10AM-4PM'}),

            'logo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'receipt_logo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'favicon': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),

            'currency_symbol': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '₦, €, etc.'}),
            'currency_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'NGN, USD, EUR, etc.'}),
            'timezone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., America/New_York, Africa/Lagos'}),
            'date_format': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '%B %d, %Y'}),

            'receipt_header_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional header text for receipts'}),
            'receipt_footer_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'show_receipt_tax_id': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            'facebook_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://facebook.com/yourpage'}),
            'instagram_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://instagram.com/yourpage'}),
            'twitter_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://twitter.com/yourpage'}),

            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def store_configuration(request):
    """Main store configuration page"""
    config = StoreConfiguration.get_active_config()
    all_configs = StoreConfiguration.objects.all().order_by('-is_active', '-updated_at')

    context = {
        'config': config,
        'all_configs': all_configs,
    }
    return render(request, 'config/store_configuration.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def edit_configuration(request, pk=None):
    """Edit store configuration"""
    if pk:
        config = get_object_or_404(StoreConfiguration, pk=pk)
    else:
        config = StoreConfiguration.get_active_config()

    if request.method == 'POST':
        form = StoreConfigurationForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            config = form.save(commit=False)
            config.updated_by = request.user
            config.save()
            messages.success(request, f"Configuration '{config.deployment_name}' updated successfully!")
            return redirect('store_configuration')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = StoreConfigurationForm(instance=config)

    return render(request, 'config/edit_configuration.html', {'form': form, 'config': config})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def add_configuration(request):
    """Add new deployment configuration"""
    if request.method == 'POST':
        form = StoreConfigurationForm(request.POST, request.FILES)
        if form.is_valid():
            config = form.save(commit=False)
            config.updated_by = request.user
            config.save()
            messages.success(request, f"New configuration '{config.deployment_name}' created successfully!")
            return redirect('store_configuration')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = StoreConfigurationForm()

    return render(request, 'config/add_configuration.html', {'form': form})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def activate_configuration(request, pk):
    """Activate a specific configuration"""
    config = get_object_or_404(StoreConfiguration, pk=pk)
    config.is_active = True
    config.save()  # Model's save will deactivate others

    messages.success(request, f"Configuration '{config.deployment_name}' is now active!")
    return redirect('store_configuration')


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def delete_configuration(request, pk):
    """Delete a configuration"""
    config = get_object_or_404(StoreConfiguration, pk=pk)

    if config.is_active:
        messages.error(request, "Cannot delete the active configuration!")
        return redirect('store_configuration')

    if request.method == 'POST':
        deployment_name = config.deployment_name
        config.delete()
        messages.success(request, f"Configuration '{deployment_name}' deleted successfully!")
        return redirect('store_configuration')

    return render(request, 'config/delete_configuration.html', {'config': config})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def preview_configuration(request, pk):
    """Preview a configuration"""
    config = get_object_or_404(StoreConfiguration, pk=pk)

    context = {
        'config': config,
    }
    return render(request, 'config/preview_configuration.html', context)


# =====================================
# LOYALTY CONFIGURATION VIEWS
# =====================================

class LoyaltyConfigurationForm(ModelForm):
    """Form for loyalty program configuration"""

    class Meta:
        model = LoyaltyConfiguration
        fields = [
            'program_name', 'is_active',
            'calculation_type', 'points_per_transaction',
            'points_per_currency_unit', 'currency_unit_value',
            'points_to_currency_rate', 'minimum_points_for_redemption',
            'maximum_discount_percentage',
            'points_expire', 'points_expiry_days',
            'send_welcome_email', 'send_points_earned_email',
            'send_points_redeemed_email', 'send_expiry_reminder_email',
            'expiry_reminder_days', 'enable_bonus_multipliers'
        ]
        widgets = {
            'program_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., VIP Rewards Program'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'calculation_type': forms.Select(attrs={'class': 'form-select'}),
            'points_per_transaction': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '1'
            }),
            'points_per_currency_unit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '1.00'
            }),
            'currency_unit_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '100.00'
            }),
            'points_to_currency_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '1.00'
            }),
            'minimum_points_for_redemption': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '100'
            }),
            'maximum_discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': '50.00'
            }),
            'points_expire': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'points_expiry_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '365'
            }),
            'send_welcome_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'send_points_earned_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'send_points_redeemed_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'send_expiry_reminder_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'expiry_reminder_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': '30'
            }),
            'enable_bonus_multipliers': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def loyalty_configuration(request):
    """Main loyalty configuration page"""
    config = LoyaltyConfiguration.get_active_config()

    # Calculate example scenario
    example_amount = Decimal('5000.00')
    example_points = config.calculate_points_earned(example_amount)
    example_discount = config.calculate_discount_from_points(100)

    context = {
        'config': config,
        'example_amount': example_amount,
        'example_points': example_points,
        'example_discount': example_discount,
    }
    return render(request, 'config/loyalty_configuration.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def edit_loyalty_configuration(request):
    """Edit loyalty configuration"""
    config = LoyaltyConfiguration.get_active_config()

    if request.method == 'POST':
        form = LoyaltyConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            loyalty_config = form.save(commit=False)
            loyalty_config.created_by = request.user
            loyalty_config.save()
            messages.success(request, "Loyalty program configuration updated successfully!")
            return redirect('loyalty_configuration')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LoyaltyConfigurationForm(instance=config)

    return render(request, 'config/edit_loyalty_configuration.html', {'form': form, 'config': config})


# =====================================
# PAYMENT METHOD CONFIGURATION VIEWS
# =====================================

class PaymentMethodForm(ModelForm):
    """Form for payment method configuration"""

    class Meta:
        model = PaymentMethodConfiguration
        fields = [
            'name', 'code', 'display_name', 'is_active',
            'icon_class', 'description', 'requires_reference', 'sort_order'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Cash Payment'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., cash',
                'pattern': '[a-z_]+',
                'title': 'Use lowercase letters and underscores only'
            }),
            'display_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Cash'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'icon_class': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., bi-cash, bi-credit-card'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description or notes'
            }),
            'requires_reference': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '0'
            }),
        }


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def payment_method_configuration(request):
    """Main payment method configuration page"""
    from .models import PaymentMethod

    methods = PaymentMethodConfiguration.objects.all().order_by('sort_order', 'display_name')

    # Get system-defined payment methods for comparison
    system_methods = PaymentMethod.PAYMENT_METHODS
    configured_codes = set(methods.values_list('code', flat=True))
    unconfigured_methods = [
        (code, name) for code, name in system_methods
        if code not in configured_codes
    ]

    context = {
        'methods': methods,
        'unconfigured_methods': unconfigured_methods,
        'system_methods': system_methods,
    }
    return render(request, 'config/payment_method_configuration.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def add_payment_method(request):
    """Add new payment method"""
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            method = form.save(commit=False)
            method.created_by = request.user
            method.save()
            messages.success(request, f"Payment method '{method.display_name}' added successfully!")
            return redirect('payment_method_configuration')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PaymentMethodForm()

    return render(request, 'config/add_payment_method.html', {'form': form})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def edit_payment_method(request, pk):
    """Edit payment method"""
    method = get_object_or_404(PaymentMethodConfiguration, pk=pk)

    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=method)
        if form.is_valid():
            method = form.save()
            messages.success(request, f"Payment method '{method.display_name}' updated successfully!")
            return redirect('payment_method_configuration')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PaymentMethodForm(instance=method)

    return render(request, 'config/edit_payment_method.html', {'form': form, 'method': method})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def delete_payment_method(request, pk):
    """Delete a payment method"""
    method = get_object_or_404(PaymentMethodConfiguration, pk=pk)

    if request.method == 'POST':
        display_name = method.display_name
        method.delete()
        messages.success(request, f"Payment method '{display_name}' deleted successfully!")
        return redirect('payment_method_configuration')

    return render(request, 'config/delete_payment_method.html', {'method': method})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def toggle_payment_method(request, pk):
    """Toggle payment method active status"""
    method = get_object_or_404(PaymentMethodConfiguration, pk=pk)
    method.is_active = not method.is_active
    method.save()

    status = "activated" if method.is_active else "deactivated"
    messages.success(request, f"Payment method '{method.display_name}' {status}!")
    return redirect('payment_method_configuration')


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def sync_payment_methods(request):
    """Sync default payment methods from PaymentMethod.PAYMENT_METHODS"""
    from .models import PaymentMethod

    if request.method == 'POST':
        created_count = 0
        updated_count = 0

        # Get all payment methods from PaymentMethod.PAYMENT_METHODS
        for code, display_name in PaymentMethod.PAYMENT_METHODS:
            # Check if payment method already exists
            method, created = PaymentMethodConfiguration.objects.get_or_create(
                code=code,
                defaults={
                    'name': display_name,
                    'display_name': display_name,
                    'is_active': True,
                    'sort_order': 0,
                    'created_by': request.user,
                }
            )

            if created:
                created_count += 1
            else:
                # Update display name if it changed
                if method.display_name != display_name or method.name != display_name:
                    method.name = display_name
                    method.display_name = display_name
                    method.save()
                    updated_count += 1

        if created_count > 0 or updated_count > 0:
            messages.success(
                request,
                f"Payment methods synchronized! Created: {created_count}, Updated: {updated_count}"
            )
        else:
            messages.info(request, "All payment methods are already up to date.")

        return redirect('payment_method_configuration')

    return redirect('payment_method_configuration')


# =====================================
# TAX CONFIGURATION VIEWS
# =====================================

class TaxConfigurationForm(ModelForm):
    """Form for tax configuration"""

    class Meta:
        model = TaxConfiguration
        fields = [
            'name', 'code', 'description', 'tax_type', 'rate',
            'calculation_method', 'is_active', 'display_on_receipt', 'sort_order'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Value Added Tax'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., VAT',
                'pattern': '[A-Z]+',
                'title': 'Use uppercase letters only'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description or notes'
            }),
            'tax_type': forms.Select(attrs={'class': 'form-select'}),
            'rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '7.5'
            }),
            'calculation_method': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_on_receipt': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '0'
            }),
        }


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def tax_configuration(request):
    """Main tax configuration page"""
    taxes = TaxConfiguration.objects.all().order_by('sort_order', 'name')

    # Calculate example for demo
    example_amount = Decimal('10000.00')
    example_calculations = []

    for tax in taxes.filter(is_active=True):
        total, tax_amount = tax.calculate_total_with_tax(example_amount)
        example_calculations.append({
            'tax': tax,
            'subtotal': example_amount,
            'tax_amount': tax_amount,
            'total': total
        })

    context = {
        'taxes': taxes,
        'example_amount': example_amount,
        'example_calculations': example_calculations,
    }
    return render(request, 'config/tax_configuration.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def add_tax(request):
    """Add new tax"""
    if request.method == 'POST':
        form = TaxConfigurationForm(request.POST)
        if form.is_valid():
            tax = form.save(commit=False)
            tax.created_by = request.user
            tax.save()
            messages.success(request, f"Tax '{tax.name}' added successfully!")
            return redirect('tax_configuration')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = TaxConfigurationForm()

    return render(request, 'config/add_tax.html', {'form': form})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def edit_tax(request, pk):
    """Edit tax"""
    tax = get_object_or_404(TaxConfiguration, pk=pk)

    if request.method == 'POST':
        form = TaxConfigurationForm(request.POST, instance=tax)
        if form.is_valid():
            tax = form.save()
            messages.success(request, f"Tax '{tax.name}' updated successfully!")
            return redirect('tax_configuration')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = TaxConfigurationForm(instance=tax)

    return render(request, 'config/edit_tax.html', {'form': form, 'tax': tax})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def delete_tax(request, pk):
    """Delete a tax"""
    tax = get_object_or_404(TaxConfiguration, pk=pk)

    if request.method == 'POST':
        name = tax.name
        tax.delete()
        messages.success(request, f"Tax '{name}' deleted successfully!")
        return redirect('tax_configuration')

    return render(request, 'config/delete_tax.html', {'tax': tax})


@login_required(login_url='login')
@user_passes_test(is_admin_or_md, login_url='access_denied')
def toggle_tax(request, pk):
    """Toggle tax active status"""
    tax = get_object_or_404(TaxConfiguration, pk=pk)
    tax.is_active = not tax.is_active
    tax.save()

    status = "activated" if tax.is_active else "deactivated"
    messages.success(request, f"Tax '{tax.name}' {status}!")
    return redirect('tax_configuration')
