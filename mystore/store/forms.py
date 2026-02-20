from django import forms
from .models import Product, PreOrder, Invoice, GoodsReceived, Delivery, Customer, Sale, Payment,UserProfile,PaymentMethod,LocationTransfer,PrinterConfiguration,PrinterTaskMapping
from django.contrib.auth.models import User
from decimal import Decimal
from django.contrib.auth.forms import UserCreationForm
from .choices import ProductChoices
from django.forms import formset_factory
import win32print


class CustomUserCreationForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Enter first name'
    }))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Enter last name'
    }))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control', 'placeholder': 'Enter email address'
    }))
    access_level = forms.ChoiceField(
        choices=UserProfile.ACCESS_LEVEL_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    phone_number = forms.CharField(max_length=15, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Enter phone number'
    }))

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter username'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Confirm password'})


class UserEditForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
        'class': 'form-control'
    }))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
        'class': 'form-control'
    }))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control'
    }))
    is_active = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={
        'class': 'form-check-input'
    }))

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('access_level', 'phone_number', 'is_active_staff')
        widgets = {
            'access_level': forms.Select(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PreOrderStatusForm(forms.ModelForm):
    class Meta:
        model = PreOrder
        fields = ['delivered']


class ProductForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set choices dynamically including custom values from database
        self.fields['color'].widget = forms.Select(
            choices=[('', '-- Select Color --')] + self._flatten_choices(ProductChoices.get_all_colors_with_custom(Product)))
        self.fields['design'].widget = forms.Select(
            choices=[('', '-- Select Design --')] + self._flatten_choices(ProductChoices.get_all_designs_with_custom(Product)))
        self.fields['category'].widget = forms.Select(
            choices=[('', '-- Select Category --')] + ProductChoices.get_all_categories_with_custom(Product))

        # Add CSS classes for better styling
        self.fields['color'].widget.attrs.update({'class': 'form-control'})
        self.fields['design'].widget.attrs.update({'class': 'form-control'})
        self.fields['category'].widget.attrs.update({'class': 'form-control'})

    def _flatten_choices(self, choices):
        """Flatten nested choice tuples for use in forms"""
        flattened = []
        for choice in choices:
            if isinstance(choice[1], tuple):
                # This is a grouped choice
                flattened.extend(choice[1])
            else:
                # This is a regular choice
                flattened.append(choice)
        return flattened

    class Meta:
        model = Product
        fields = ['brand', 'price', 'color', 'design', 'size', 'category',
                  'quantity', 'markup_type', 'markup', 'shop', 'barcode_number', 'image']
        widgets = {
            'brand': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'size': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'markup': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'barcode_number': forms.TextInput(attrs={'class': 'form-control'}),
            'markup_type': forms.Select(attrs={'class': 'form-control'}),
            'shop': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }


class ProductFilterForm(forms.Form):
    """Form for filtering products in the product list view"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by brand, color, category...'
        })
    )

    category = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    color = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    design = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    shop = forms.ChoiceField(
        required=False,
        choices=[('', 'All Shops')] + ProductChoices.SHOP_TYPE,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    size = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Size'
        })
    )

    min_price = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min Price',
            'step': '0.01'
        })
    )

    max_price = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max Price',
            'step': '0.01'
        })
    )

    min_quantity = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min Qty'
        })
    )

    max_quantity = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max Qty'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set dynamic choices for filter form
        self.fields['category'].choices = [('', 'All Categories')] + Product.get_all_categories_with_custom()
        self.fields['color'].choices = [('', 'All Colors')] + self._flatten_choices(
            Product.get_all_colors_with_custom())
        self.fields['design'].choices = [('', 'All Designs')] + self._flatten_choices(
            Product.get_all_designs_with_custom())

    def _flatten_choices(self, choices):
        """Flatten nested choice tuples for use in forms"""
        flattened = []
        for choice in choices:
            if isinstance(choice[1], tuple):
                # This is a grouped choice
                flattened.extend(choice[1])
            else:
                # This is a regular choice
                flattened.append(choice)
        return flattened


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'email', 'phone_number', 'address', 'sex', 'frequent_customer']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control form-control-lg rounded-12',
                'placeholder': 'Mr/Mrs/Ms Best Customer'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control form-control-lg rounded-12',
                'placeholder': 'customer@domain.com (Optional)'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control form-control-lg rounded-12',
                'placeholder': '+234 800 000 0000'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control rounded-12',
                'rows': 3,
                'placeholder': 'Enter full address'
            }),
            'sex': forms.Select(attrs={
                'class': 'form-control form-select-lg rounded-12'
            }),
            'frequent_customer': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(CustomerForm, self).__init__(*args, **kwargs)

        # Only name is required
        self.fields['name'].required = True

        # All other fields are optional
        self.fields['email'].required = False
        self.fields['phone_number'].required = False
        self.fields['address'].required = False
        self.fields['sex'].required = False
        self.fields['frequent_customer'].required = False

        # Clear default values for new customers (show placeholders instead)
        if not self.instance.pk:
            self.initial['name'] = ''
            self.initial['email'] = ''
            self.initial['phone_number'] = ''

        # Format phone number for display: ensure it starts with +234
        if self.instance.pk and self.instance.phone_number:
            phone = self.instance.phone_number.strip()
            if phone.startswith('0'):
                phone = '+234' + phone[1:]
            elif not phone.startswith('+234'):
                phone = '+234' + phone
            self.initial['phone_number'] = phone

        # Update placeholder to show optional status
        self.fields['phone_number'].widget.attrs['placeholder'] = '+234 800 000 0000 (Optional)'
        self.fields['address'].widget.attrs['placeholder'] = 'Enter complete address with street, city, and state (Optional)'
        self.fields['sex'].widget.attrs['placeholder'] = 'Select gender (Optional)'

    def clean_phone_number(self):
        phone = (self.cleaned_data.get('phone_number') or '').strip()

        # If phone number is empty or just the default prefix, allow it (field is optional)
        if not phone or phone == '+234' or phone == '234':
            return ''

        # Remove common formatting
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')

        # Validate Nigerian number (10 or 11 digits after 234)
        if len(phone) == 10 and phone.startswith('0'):
            phone = '234' + phone[1:]
        elif len(phone) == 11 and phone.startswith('0'):
            phone = '234' + phone[1:]
        elif len(phone) == 10:
            phone = '234' + phone
        elif len(phone) == 13 and phone.startswith('234'):
            pass  # Already in correct format
        else:
            raise forms.ValidationError("Enter a valid Nigerian phone number (e.g., 08012345678 or +2348012345678).")

        return '+' + phone


class PreOrderForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set choices dynamically including custom values from database
        self.fields['color'].widget = forms.Select(
            choices=[('', '-- Select Color --')] + self._flatten_choices(ProductChoices.get_all_colors_with_custom(Product)))
        self.fields['design'].widget = forms.Select(
            choices=[('', '-- Select Design --')] + self._flatten_choices(ProductChoices.get_all_designs_with_custom(Product)))
        self.fields['category'].widget = forms.Select(
            choices=[('', '-- Select Category --')] + ProductChoices.get_all_categories_with_custom(Product))

        # Add CSS classes for better styling
        self.fields['color'].widget.attrs.update({'class': 'form-control'})
        self.fields['design'].widget.attrs.update({'class': 'form-control'})
        self.fields['category'].widget.attrs.update({'class': 'form-control'})

        # Make only pre-order fields required, purchase fields are optional
        self.fields['brand'].required = True
        self.fields['customer'].required = True
        self.fields['quantity'].required = True

        # Purchase fields are optional (fill in later before conversion)
        self.fields['price'].required = False
        self.fields['markup_type'].required = False
        self.fields['markup'].required = False
        self.fields['selling_price'].required = False
        self.fields['shop'].required = False
        self.fields['barcode_number'].required = False
        self.fields['location'].required = False

        # Product spec fields are optional
        self.fields['size'].required = False
        self.fields['color'].required = False
        self.fields['design'].required = False
        self.fields['category'].required = False

    def _flatten_choices(self, nested_choices):
        """Flatten nested choices for Select widget"""
        flattened = []
        for item in nested_choices:
            if isinstance(item[1], list):
                flattened.extend(item[1])
            else:
                flattened.append(item)
        return flattened

    class Meta:
        model = PreOrder
        fields = [
            'brand',
            'customer',
            'quantity',
            'size',
            'color',
            'design',
            'category',
            'price',
            'markup_type',
            'markup',
            'selling_price',
            'shop',
            'barcode_number',
            'location',
            'delivery_date',
            'delivered',
            'remarks',
        ]
        widgets = {
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product Brand/Model'}),
            'customer': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'How many units?'}),
            'size': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Size (optional)'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Buying price (add when purchased)'}),
            'markup_type': forms.Select(attrs={'class': 'form-control'}),
            'markup': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Markup (add when purchased)'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Auto-calculated or manual'}),
            'shop': forms.Select(attrs={'class': 'form-control'}),
            'barcode_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Barcode (optional)'}),
            'location': forms.Select(attrs={'class': 'form-control'}),
            'delivery_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'delivered': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Any additional notes'}),
        }




class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        exclude = ['invoice_number']  # Don't exclude user field



class GoodsReceivedForm(forms.ModelForm):
    class Meta:
        model = GoodsReceived
        fields = ['product', 'quantity_received', 'batch_number']




class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))


class ExcelUploadForm(forms.Form):
    excel_file = forms.FileField(
        label='Excel File',
        help_text='Upload an Excel file (.xlsx or .xls) with product data',
        widget=forms.FileInput(attrs={
            'accept': '.xlsx,.xls',
            'class': 'form-control'
        })
    )
    overwrite_existing = forms.BooleanField(
        required=False,
        initial=False,
        label='Overwrite existing products',
        help_text='Check this box to update products with matching barcodes. Leave unchecked to skip duplicates.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def clean_excel_file(self):
        excel_file = self.cleaned_data['excel_file']

        # Check file extension
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            raise forms.ValidationError('Please upload a valid Excel file (.xlsx or .xls)')

        # Check file size (limit to 10MB)
        if excel_file.size > 10 * 1024 * 1024:  # 10MB
            raise forms.ValidationError('File size must be less than 10MB')

        return excel_file


class TransferItemForm(forms.Form):
    selected = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'product-checkbox'}))
    product_id = forms.IntegerField(widget=forms.HiddenInput())
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control quantity-input', 'disabled': True})
    )

    def __init__(self, *args, **kwargs):
        product = kwargs.pop('product', None)
        super().__init__(*args, **kwargs)

        if product:
            self.fields['product_id'].initial = product.id
            self.fields['quantity'].widget.attrs['max'] = product.quantity


class LocationTransferForm(forms.ModelForm):
    class Meta:
        model = LocationTransfer
        fields = ['to_location', 'notes']
        widgets = {
            'to_location': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class InternalTransferForm(forms.Form):
    """Form for internal transfers from Warehouse"""
    DESTINATION_CHOICES = [
        ('STORE', 'Shop Floor (Same Location)'),
        ('ABUJA', 'Abuja'),
        ('LAGOS', 'Lagos'),
    ]

    destination = forms.ChoiceField(
        choices=DESTINATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Transfer To'
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes...'}),
        label='Notes'
    )



class PaymentMethodForm(forms.ModelForm):
    """Form for individual payment method"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set dynamic choices from PaymentMethod
        self.fields['payment_method'].choices = PaymentMethod.get_payment_method_choices()

    class Meta:
        model = PaymentMethod
        fields = ['payment_method', 'amount', 'reference_number', 'notes']
        widgets = {
            'payment_method': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control payment-amount',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
                'required': True
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Reference number (optional)',
                'maxlength': 100
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Additional notes (optional)',
                'maxlength': 500
            })
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        # Allow 0 or None for gift transactions (validation happens in view)
        if amount is not None and amount < 0:
            raise forms.ValidationError("Payment amount cannot be negative")
        return amount

class BasePaymentMethodForm(PaymentMethodForm):
    """Base form with delete functionality for formsets"""
    DELETE = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make amount field not required by default for empty forms
        if not self.initial and not self.data:
            self.fields['amount'].required = False
            self.fields['payment_method'].required = False

# Create the formset
PaymentMethodFormSet = formset_factory(
    BasePaymentMethodForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)

class PaymentForm(forms.ModelForm):
    """Main payment form"""
    class Meta:
        model = Payment
        fields = ['discount_percentage']
        widgets = {
            'discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': '0.00'
            })
        }

    def clean_discount_percentage(self):
        discount = self.cleaned_data.get('discount_percentage')
        if discount and (discount < 0 or discount > 100):
            raise forms.ValidationError("Discount percentage must be between 0 and 100")
        return discount

class SaleForm(forms.ModelForm):
    """Updated sale form - minimal changes"""
    class Meta:
        model = Sale
        fields = ['product', 'quantity', 'discount_amount', 'is_gift', 'gift_reason']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-control product-select',
                'required': True
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control quantity-input',
                'min': '1',
                'value': '1'
            }),
            'discount_amount': forms.NumberInput(attrs={
                'class': 'form-control discount-input',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'is_gift': forms.CheckboxInput(attrs={
                'class': 'form-check-input gift-checkbox',
            }),
            'gift_reason': forms.Textarea(attrs={
                'class': 'form-control gift-reason-input',
                'rows': 2,
                'placeholder': 'Reason for gift (optional)'
            })
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Only show gift fields to superusers or MD (admin) users
        is_admin = False
        if user:
            if user.is_superuser:
                is_admin = True
            elif hasattr(user, 'userprofile') and user.userprofile.access_level == 'md':
                is_admin = True

        if not is_admin:
            # Remove gift fields for non-admin users
            self.fields.pop('is_gift', None)
            self.fields.pop('gift_reason', None)


class DeliveryForm(forms.ModelForm):
    """Delivery form with corrected date handling"""

    class Meta:
        model = Delivery
        fields = ['delivery_option', 'delivery_cost', 'delivery_address', 'delivery_date', 'delivery_status']
        widgets = {
            'delivery_option': forms.Select(attrs={'class': 'form-select'}),
            'delivery_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'delivery_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'delivery_date': forms.DateInput(attrs={  # Changed from DateTimeInput to DateInput
                'class': 'form-control',
                'type': 'date'  # Changed from 'datetime-local' to 'date'
            }),
            'delivery_status': forms.Select(attrs={'class': 'form-select'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set default values for new deliveries (when no instance is provided)
        if not self.instance.pk:
            from datetime import date
            self.initial['delivery_option'] = 'pickup'
            self.initial['delivery_date'] = date.today()
            self.initial['delivery_status'] = 'delivered'

    def clean_delivery_date(self):
        """Ensure delivery_date is properly formatted"""
        delivery_date = self.cleaned_data.get('delivery_date')
        if delivery_date:
            # If it's a string, try to parse it
            if isinstance(delivery_date, str):
                try:
                    # Try to parse as date (YYYY-MM-DD)
                    return datetime.strptime(delivery_date, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        # Try to parse as datetime (YYYY-MM-DDTHH:MM)
                        return datetime.strptime(delivery_date, '%Y-%m-%dT%H:%M').date()
                    except ValueError:
                        raise forms.ValidationError("Enter a valid date in YYYY-MM-DD format.")
        return delivery_date

# Utility form for payment validation
class PaymentValidationForm(forms.Form):
    """Validation form to ensure payment methods sum correctly"""
    total_sale_amount = forms.DecimalField(widget=forms.HiddenInput())
    payment_methods_total = forms.DecimalField(widget=forms.HiddenInput())

    def clean(self):
        cleaned_data = super().clean()
        total_sale = cleaned_data.get('total_sale_amount', Decimal('0'))
        payments_total = cleaned_data.get('payment_methods_total', Decimal('0'))

        # Allow some tolerance for rounding
        tolerance = Decimal('0.01')
        difference = abs(total_sale - payments_total)

        if difference > tolerance:
            if payments_total > total_sale:
                raise forms.ValidationError(
                    f"Payment methods total (₦{payments_total:.2f}) exceeds sale amount (₦{total_sale:.2f}) by ₦{difference:.2f}"
                )
            else:
                raise forms.ValidationError(
                    f"Payment methods total (₦{payments_total:.2f}) is ₦{difference:.2f} short of sale amount (₦{total_sale:.2f})"
                )

        return cleaned_data


class PrinterConfigurationForm(forms.ModelForm):
    """Form for configuring printers"""

    class Meta:
        model = PrinterConfiguration
        fields = [
            'name', 'printer_type', 'system_printer_name', 'paper_size',
            'paper_width_mm', 'paper_height_mm', 'is_default', 'is_active',
            'auto_print', 'dpi', 'copies', 'barcode_width', 'barcode_height'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Main POS Printer'
            }),
            'printer_type': forms.Select(attrs={'class': 'form-control'}),
            'system_printer_name': forms.Select(attrs={'class': 'form-control'}),
            'paper_size': forms.Select(attrs={'class': 'form-control'}),
            'paper_width_mm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Width in mm'
            }),
            'paper_height_mm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Height in mm'
            }),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_print': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dpi': forms.NumberInput(attrs={'class': 'form-control'}),
            'copies': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'barcode_width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '50'
            }),
            'barcode_height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '25'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate system printer names from Windows
        try:
            printers = []
            printer_enum = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)

            for printer in printer_enum:
                printer_name = printer[2]  # Printer name is at index 2
                printers.append((printer_name, printer_name))

            # Update the field to be a select with available printers
            self.fields['system_printer_name'].widget = forms.Select(
                choices=[('', '--- Select Printer ---')] + printers,
                attrs={'class': 'form-control'}
            )
        except Exception as e:
            # Fallback to text input if can't enumerate printers
            self.fields['system_printer_name'].widget = forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter exact printer name'
            })

    def clean(self):
        cleaned_data = super().clean()
        paper_size = cleaned_data.get('paper_size')
        paper_width = cleaned_data.get('paper_width_mm')
        paper_height = cleaned_data.get('paper_height_mm')

        # If custom size is selected, require width and height
        if paper_size == 'custom':
            if not paper_width or not paper_height:
                raise forms.ValidationError(
                    "For custom paper size, please specify both width and height"
                )

        return cleaned_data


class PrinterTaskMappingForm(forms.ModelForm):
    """Form for mapping tasks to printers"""

    class Meta:
        model = PrinterTaskMapping
        fields = ['task_name', 'printer', 'is_active', 'auto_print', 'copies', 'notes']
        widgets = {
            'task_name': forms.Select(attrs={'class': 'form-control'}),
            'printer': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_print': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'copies': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '10'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional notes about this task mapping...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter printer choices to only active printers
        self.fields['printer'].queryset = PrinterConfiguration.objects.filter(is_active=True)
        self.fields['printer'].empty_label = "--- Select Printer ---"