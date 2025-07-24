import phonenumbers
from phonenumbers import carrier, geocoder

def validate_phone(phone):
    try:
        parsed = phonenumbers.parse(phone, "RU")  # 'RU' для России
        return phonenumbers.is_valid_number(parsed)
    except phonenumbers.phonenumberutil.NumberParseException:
        return False