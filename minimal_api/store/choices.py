# choices.py
from django.db.models import Q


class ProductChoices:
    SHOP_TYPE = [
        ('STORE', 'Store (Shop Floor)'),
        ('WAREHOUSE', 'Warehouse'),
    ]

    MARKUP_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]

    COLOR_CHOICES = [
        ('Black Family', [
            ('Black', 'Black'),
            ('Jet Black', 'Jet Black'),
            ('Charcoal', 'Charcoal'),
            ('Onyx', 'Onyx'),
            ('Dirty Black', 'Dirty Black'),
            ('Black and Carton', 'Black and Carton'),
            ('Black and White', 'Black and White'),
            ('Black with Blue Design', 'Black with Blue Design'),
            ('Black/Blue/Green', 'Black/Blue/Green'),
            ('Black/White', 'Black/White'),
            ('Black/whitestripes', 'Black/whitestripes'),
        ]),
        ('Brown Family', [
            ('Brown', 'Brown'),
            ('Chocolate', 'Chocolate'),
            ('Coffee', 'Coffee'),
            ('Mocha', 'Mocha'),
            ('Walnut', 'Walnut'),
            ('Taupe', 'Taupe'),
            ('Tan', 'Tan'),
            ('Camel', 'Camel'),
            ('Carton', 'Carton'),
            ('Carton Brown', 'Carton Brown'),
            ('Dark Carton', 'Dark Carton'),
            ('Light Carton', 'Light Carton'),
            ('Yellow Carton', 'Yellow Carton'),
            ('Ash/Brown Plaid', 'Ash/Brown Plaid'),
            ('Brown Checkered', 'Brown Checkered'),
            ('Brown Plaid', 'Brown Plaid'),
            ('Brown Stripes', 'Brown Stripes'),
        ]),
        ('White Family', [
            ('White', 'White'),
            ('Ivory', 'Ivory'),
            ('Cream', 'Cream'),
            ('Eggshell', 'Eggshell'),
            ('Linen', 'Linen'),
            ('Off-White', 'Off-White'),
            ('Cream/Greyish', 'Cream/Greyish'),
            ('Cream/navy blue', 'Cream/navy blue'),
            ('Cream/sky blue', 'Cream/sky blue'),
            ('White & Grey Green Stripes', 'White & Grey Green Stripes'),
            ('White and Green Plaids', 'White and Green Plaids'),
            ('White and Green Stripes', 'White and Green Stripes'),
            ('White & Black Small Dot Plaids', 'White & Black Small Dot Plaids'),
            ('White with Dots', 'White with Dots'),
            ('white/brown embroidered', 'white/brown embroidered'),
        ]),
        ('Blue Family', [
            ('Blue', 'Blue'),
            ('Dark Blue', 'Dark Blue'),
            ('Sky Blue', 'Sky Blue'),
            ('Royal Blue', 'Royal Blue'),
            ('Baby Blue', 'Baby Blue'),
            ('Cobalt', 'Cobalt'),
            ('Powder Blue', 'Powder Blue'),
            ('Faded Blue', 'Faded Blue'),
            ('Denim Blue', 'Denim Blue'),
            ('Linen Blue', 'Linen Blue'),
            ('Regular Blue', 'Regular Blue'),
            ('Blue & Pink', 'Blue & Pink'),
            ('Blue Stripes', 'Blue Stripes'),
            ('Blue/Black', 'Blue/Black'),
            ('Blue/Grey', 'Blue/Grey'),
            ('Blue/lime green', 'Blue/lime green'),
            ('Blue/Navy Checkered', 'Blue/Navy Checkered'),
            ('Navy Blue', 'Navy Blue'),
            ('Navy Blue & Cream', 'Navy Blue & Cream'),
            ('Navy Blue & White Plaids', 'Navy Blue & White Plaids'),
            ('Navy Blue Striped', 'Navy Blue Striped'),
            ('Navy Blue Stripes', 'Navy Blue Stripes'),
            ('Navy Checkered', 'Navy Checkered'),
        ]),
        ('Gray Family', [
            ('Gray', 'Gray'),
            ('Grey', 'Grey'),
            ('Ash', 'Ash'),
            ('Ash Grey', 'Ash Grey'),
            ('Ash & Grey', 'Ash & Grey'),
            ('Slate', 'Slate'),
            ('Smoke', 'Smoke'),
            ('Silver', 'Silver'),
            ('Dark Grey', 'Dark Grey'),
            ('Grey Plaid', 'Grey Plaid'),
            ('Grey Striped', 'Grey Striped'),
            ('Grey Green Stripes', 'Grey Green Stripes'),
            ('Green/Gray Plaid', 'Green/Gray Plaid'),
        ]),
        ('Red Family', [
            ('Red', 'Red'),
            ('Burgundy', 'Burgundy'),
            ('Crimson', 'Crimson'),
            ('Wine', 'Wine'),
            ('Maroon', 'Maroon'),
            ('Light Wine', 'Light Wine'),
            ('Maroon with Blue Stripes', 'Maroon with Blue Stripes'),
            ('Maroon/Cream Plaid', 'Maroon/Cream Plaid'),
            ('Red & White', 'Red & White'),
            ('Red/Multi-color', 'Red/Multi-color'),
        ]),
        ('Green Family', [
            ('Green', 'Green'),
            ('Dark Green', 'Dark Green'),
            ('Olive', 'Olive'),
            ('Olive Green & White', 'Olive Green & White'),
            ('Mint', 'Mint'),
            ('Mint Cream', 'Mint Cream'),
            ('Mint green and navy blue', 'Mint green and navy blue'),
            ('Mint Green Striped', 'Mint Green Striped'),
            ('Sage', 'Sage'),
            ('Emerald', 'Emerald'),
            ('Army Green', 'Army Green'),
            ('Plant Green', 'Plant Green'),
            ('Lime Green', 'Lime Green'),
            ('Teal', 'Teal'),
            ('Palm Green', 'Palm Green'),
        ]),
        ('Pink Family', [
            ('Pink', 'Pink'),
            ('Rose', 'Rose'),
            ('Hot Pink', 'Hot Pink'),
            ('Blush', 'Blush'),
            ('Fuchsia', 'Fuchsia'),
            ('Peach', 'Peach'),
            ('Pink & Brown Flowers', 'Pink & Brown Flowers'),
        ]),
        ('Purple Family', [
            ('Purple', 'Purple'),
            ('Lavender', 'Lavender'),
            ('Plum', 'Plum'),
            ('Mauve', 'Mauve'),
            ('Orchid', 'Orchid'),
            ('Lilac', 'Lilac'),
            ('Lilac/Striped', 'Lilac/Striped'),
            ('Puple & Lilac', 'Puple & Lilac'),
            ('Dark Ash & Purple', 'Dark Ash & Purple'),
        ]),
        ('Beige Family', [
            ('Beige', 'Beige'),
            ('Sand', 'Sand'),
            ('Khaki', 'Khaki'),
            ('Khahi', 'Khahi'),
            ('Oatmeal', 'Oatmeal'),
            ('Stone', 'Stone'),
            ('Light Brown', 'Light Brown'),
            ('Light Carton', 'Light Carton'),
        ]),
        ('Orange Family', [
            ('Orange', 'Orange'),
            ('Orange Flowers', 'Orange Flowers'),
            ('Orange Plaid', 'Orange Plaid'),
        ]),
        ('Yellow Family', [
            ('Yellow', 'Yellow'),
            ('Mustard Yellow', 'Mustard Yellow'),
            ('Yellow Carton', 'Yellow Carton'),
        ]),
        ('Special Colors', [
            ('Multi color', 'Multi color'),
            ('Multi-Color', 'Multi-Color'),
            ('Rainbow', 'Rainbow'),
            ('Camou', 'Camou'),
            ('Dirty Jeans', 'Dirty Jeans'),
            ('Regular', 'Regular'),
            ('Plaids', 'Plaids'),
            ('Cotton', 'Cotton'),
            ('Organic Cotton', 'Organic Cotton'),
            ('Dark', 'Dark'),
            ('Faded Green', 'Faded Green'),
            ('Light Purple & White Stripes', 'Light Purple & White Stripes'),
            ('Hawaii Print', 'Hawaii Print'),
            ('Blue Flowers', 'Blue Flowers'),
            ('Striped', 'Striped'),
            ('Milk', 'Milk'),
            ('Milk Printed', 'Milk Printed'),
        ]),
    ]

    CATEGORY_CHOICES = [
        ('Apparel Type', [
            ('T-Shirts', 'T-Shirts'),
            ('Polos', 'Polos'),
            ('Shirts', 'Shirts'),
            ('Button Shirts', 'Button Shirts'),
            ('Office Shirts', 'Office Shirts'),
            ('Linen Shirts', 'Linen Shirts'),
            ('Sweaters', 'Sweaters'),
            ('Hoodie Set', 'Hoodie Set'),
            ('Suits', 'Suits'),
            ('Chinos', 'Chinos'),
            ('Jeans', 'Jeans'),
            ('Cargo Pants', 'Cargo Pants'),
            ('Joggers', 'Joggers'),
            ('Linen Trousers', 'Linen Trousers'),
            ('Sweatpants', 'Sweatpants'),
            ('Trousers', 'Trousers'),  # generic fallback
            ('Boxers', 'Boxers'),
            ('Briefs', 'Briefs'),
            ('Socks', 'Socks'),
            ('Towels', 'Towels'),
        ]),
        ('Outerwear', [
            ('Denim Jacket', 'Denim Jacket'),
            ('Fur Jacket', 'Fur Jacket'),
        ]),
        ('Accessories', [
            ('Caps', 'Caps'),
            ('Bucket Hats', 'Bucket Hats'),
            ('Belts', 'Belts'),
            ('Wallets', 'Wallets'),
        ]),
        ('Pattern: Plain / Solid', [
            ('Plain', 'Plain'),
            ('Solid', 'Solid'),
        ]),
        ('Pattern: Stripes', [
            ('Pinstripe', 'Pinstripe'),
            ('Chalk Stripe', 'Chalk Stripe'),
            ('Bengal Stripe', 'Bengal Stripe'),
            ('Breton Stripe', 'Breton Stripe'),
            ('Blue Stripes', 'Blue Stripes'),
            ('Navy Blue Stripes', 'Navy Blue Stripes'),
            ('Light Purple & White Stripes', 'Light Purple & White Stripes'),
            ('White & Green Stripes', 'White & Green Stripes'),
            ('Grey Green Stripes', 'Grey Green Stripes'),
            ('Sky Blue Stripes', 'Sky Blue Stripes'),
            ('Maroon with Blue Stripes', 'Maroon with Blue Stripes'),
            ('Mint Green Stripes', 'Mint Green Stripes'),
        ]),
        ('Pattern: Checks / Plaids', [
            ('Gingham', 'Gingham'),
            ('Tartan / Plaid', 'Tartan / Plaid'),
            ('Windowpane', 'Windowpane'),
            ('Tattersall', 'Tattersall'),
            ('Madras', 'Madras'),
            ('Brown Plaid', 'Brown Plaid'),
            ('Grey Plaid', 'Grey Plaid'),
            ('Green & Grey Plaid', 'Green & Grey Plaid'),
            ('Navy Blue & White Plaids', 'Navy Blue & White Plaids'),
            ('Ash/Brown Plaid', 'Ash/Brown Plaid'),
            ('Orange Plaid', 'Orange Plaid'),
            ('Maroon/Cream Plaid', 'Maroon/Cream Plaid'),
            ('Lilac/Striped', 'Lilac/Striped'),
            ('Blue/Navy Checkered', 'Blue/Navy Checkered'),
            ('Brown Checkered', 'Brown Checkered'),
        ]),
        ('Pattern: Dots', [
            ('Polka Dot', 'Polka Dot'),
            ('Microdot', 'Microdot'),
            ('White & Black Small Dot Plaids', 'White & Black Small Dot Plaids'),
            ('White with Dots', 'White with Dots'),
        ]),
        ('Pattern: Classic', [
            ('Houndstooth', 'Houndstooth'),
            ('Herringbone', 'Herringbone'),
        ]),
        ('Pattern: Artistic', [
            ('Paisley', 'Paisley'),
            ('Geometric', 'Geometric'),
            ('Abstract', 'Abstract'),
            ('Graphic / Printed', 'Graphic / Printed'),
        ]),
        ('Pattern: Casual / Modern', [
            ('Camouflage', 'Camouflage'),
            ('Floral', 'Floral'),
            ('Hawaii Print', 'Hawaii Print'),
            ('Blue Flowers', 'Blue Flowers'),
            ('Orange Flowers', 'Orange Flowers'),
            ('Pink & Brown Flowers', 'Pink & Brown Flowers'),
        ]),
    ]

    DESIGN_CHOICES = [
        ('Plain / Solid', [
            ('plain', 'Plain'),
            ('solid', 'Solid'),
        ]),
        ('Stripes', [
            ('pinstripe', 'Pinstripe'),
            ('chalk_stripe', 'Chalk Stripe'),
            ('bengal_stripe', 'Bengal Stripe'),
            ('breton_stripe', 'Breton Stripe'),
        ]),
        ('Checks / Plaids', [
            ('gingham', 'Gingham'),
            ('tartan', 'Tartan / Plaid'),
            ('windowpane', 'Windowpane'),
            ('tattersall', 'Tattersall'),
            ('madras', 'Madras'),
        ]),
        ('Dots', [
            ('polka_dot', 'Polka Dot'),
            ('microdot', 'Microdot'),
        ]),
        ('Classic Patterns', [
            ('houndstooth', 'Houndstooth'),
            ('herringbone', 'Herringbone'),
        ]),
        ('Artistic', [
            ('paisley', 'Paisley'),
            ('geometric', 'Geometric'),
            ('abstract', 'Abstract'),
        ]),
        ('Casual / Modern', [
            ('camouflage', 'Camouflage'),
            ('floral', 'Floral'),
            ('graphic', 'Graphic / Printed'),
        ]),
    ]

    @classmethod
    def get_display_value(cls, choices_list, value):
        """Get display name for a value from choices list"""
        if not value:
            return None

        # Convert value to string for comparison
        value_str = str(value)

        # Search through grouped choices
        for group in choices_list:
            if isinstance(group[1], list):
                # This is a grouped choice (like ['Basic Colors', [('red', 'Red'), ('blue', 'Blue')]])
                for val, label in group[1]:
                    if str(val) == value_str:
                        return label
            else:
                # This is a simple choice (like ('red', 'Red'))
                if str(group[0]) == value_str:
                    return group[1]

        # Fallback: format the value nicely if not found in predefined choices
        return value_str.replace('_', ' ').title() if isinstance(value, str) else str(value)

    @classmethod
    def get_all_colors_with_custom(cls, model_class):
        """Get all colors including custom ones from database"""
        # Get all predefined colors from nested structure
        predefined = set()
        for group in cls.COLOR_CHOICES:
            if isinstance(group[1], list):
                # Nested choices like ['Basic Colors', [('red', 'Red'), ('blue', 'Blue')]]
                predefined.update(choice[0] for choice in group[1])
            else:
                # Simple choices like ('red', 'Red')
                predefined.add(group[0])

        # Get custom colors from database
        custom_colors = model_class.objects.filter(
            color__isnull=False
        ).exclude(
            Q(color='') | Q(color__in=predefined)
        ).values_list('color', flat=True).distinct()

        # Filter out empty/whitespace colors
        custom_colors = [c for c in custom_colors if c and c.strip()]

        # Create deep copy of existing choices
        all_choices = []
        for group in cls.COLOR_CHOICES:
            if isinstance(group[1], list):
                all_choices.append([group[0], list(group[1])])
            else:
                all_choices.append(list(group))

        # Add custom colors as a new group if any exist
        if custom_colors:
            custom_list = [(c, c.replace('_', ' ').title()) for c in custom_colors]
            all_choices.append(['Custom Colors', custom_list])

        return all_choices

    @classmethod
    def get_all_designs_with_custom(cls, model_class):
        """Get all designs including custom ones from database"""
        # Get all predefined designs from nested structure
        predefined = set()
        for group in cls.DESIGN_CHOICES:
            if isinstance(group[1], list):
                predefined.update(choice[0] for choice in group[1])
            else:
                predefined.add(group[0])

        # Get custom designs from database
        custom_designs = model_class.objects.filter(
            design__isnull=False
        ).exclude(
            Q(design='') | Q(design__in=predefined)
        ).values_list('design', flat=True).distinct()

        # Filter out empty/whitespace designs
        custom_designs = [d for d in custom_designs if d and d.strip()]

        # Create deep copy of existing choices
        all_choices = []
        for group in cls.DESIGN_CHOICES:
            if isinstance(group[1], list):
                all_choices.append([group[0], list(group[1])])
            else:
                all_choices.append(list(group))

        # Add custom designs as a new group if any exist
        if custom_designs:
            custom_list = [(d, d.replace('_', ' ').title()) for d in custom_designs]
            all_choices.append(['Custom Designs', custom_list])

        return all_choices

    @classmethod
    def get_all_categories_with_custom(cls, model_class):
        """Get all categories including custom ones from database"""
        # Get all predefined categories from nested structure
        predefined = set()
        for group in cls.CATEGORY_CHOICES:
            if isinstance(group[1], list):
                predefined.update(choice[0] for choice in group[1])
            else:
                predefined.add(group[0])

        # Get custom categories from database
        custom_categories = model_class.objects.filter(
            category__isnull=False
        ).exclude(
            Q(category='') | Q(category__in=predefined)
        ).values_list('category', flat=True).distinct()

        # Filter out empty/whitespace categories
        custom_categories = [c for c in custom_categories if c and c.strip()]

        # Create deep copy of existing choices
        all_choices = []
        for group in cls.CATEGORY_CHOICES:
            if isinstance(group[1], list):
                all_choices.append([group[0], list(group[1])])
            else:
                all_choices.append(list(group))

        # Add custom categories as individual choices (not grouped)
        for category in custom_categories:
            all_choices.append((category, category.replace('_', ' ').title()))

        return all_choices

    @classmethod
    def debug_display_value(cls, choices_list, value):
        """Debug method to help troubleshoot display value issues"""
        for i, group in enumerate(choices_list):
            print(f"  Group {i}: {group}")
            if isinstance(group[1], list):
                print(f"    Nested choices:")
                for j, choice in enumerate(group[1]):
                    print(f"      {j}: {choice}")

        result = cls.get_display_value(choices_list, value)
        return result