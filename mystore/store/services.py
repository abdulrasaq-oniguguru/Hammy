from decimal import Decimal
from datetime import date, datetime


def clamp_discount(discount_amount, item_total):
    """Discount cannot exceed line total."""
    if discount_amount is None:
        return Decimal('0')
    return min(Decimal(str(discount_amount)), Decimal(str(item_total)))


def calculate_sale_line_total(selling_price, quantity, discount_amount):
    """selling_price × qty − discount. No DB needed."""
    selling_price = Decimal(str(selling_price))
    quantity = Decimal(str(quantity))
    discount_amount = Decimal(str(discount_amount)) if discount_amount else Decimal('0')
    return selling_price * quantity - discount_amount


def determine_payment_status(total_amount, total_paid):
    """Returns (status, balance_due, completed_date). Pure function."""
    total_amount = Decimal(str(total_amount))
    total_paid = Decimal(str(total_paid))
    balance_due = total_amount - total_paid
    if total_paid >= total_amount:
        from datetime import date
        return ('completed', Decimal('0'), date.today())
    elif total_paid > 0:
        return ('partial', balance_due, None)
    else:
        return ('pending', balance_due, None)


def generate_sequential_number(model_class, prefix, date_format='%m/%Y'):
    """Derive next auto-number (INV/RCPT/RET/SC) from last DB record."""
    from datetime import date
    today = date.today()
    date_str = today.strftime(date_format)
    last = model_class.objects.order_by('-id').first()
    if last:
        try:
            last_num = int(last.receipt_number.split('/')[0].replace(prefix, '').strip()) if hasattr(last, 'receipt_number') else 0
        except (ValueError, AttributeError, IndexError):
            last_num = 0
    else:
        last_num = 0
    return f"{prefix}{last_num + 1:03d}/{date_str}"
