import pycountry

# Membuat dictionary otomatis untuk seluruh dunia
iso_dict = {country.alpha_2: country.name for country in pycountry.countries}

# Contoh output: {'ID': 'Indonesia', 'US': 'United States', ...}

