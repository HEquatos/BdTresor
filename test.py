import pandas as pd
from datetime import datetime, date



def get_duree_dernier_coupon(date_valeur, date_emission):
# Convertir les dates en objets datetime
    if not isinstance(date_valeur, date):
        date_valeur = datetime.strptime(date_valeur, "%d/%m/%Y").date()  # Assuming date_valeur is in ISO format "YYYY-MM-DD"
    if not isinstance(date_emission, date):
        date_emission = datetime.strptime(date_emission, "%d/%m/%Y").date()  # Assuming date_emission is in ISO format "YYYY-MM-DD"
        
        
        
    # Vérification de la date du dernier coupon
    if date_emission.month < date_valeur.month:
        date_dernier_coupon = date_emission.replace(year=date_valeur.year)
    elif date_emission.month == date_valeur.month:
        if date_emission.day <= date_valeur.day:
            date_dernier_coupon = date_emission.replace(year=date_valeur.year)
        else:
            date_dernier_coupon = date_emission.replace(year=date_valeur.year - 1)
    else:
        date_dernier_coupon = date_emission.replace(year=date_valeur.year - 1)

    # Calcul de la durée écoulée en jours depuis le dernier paiement
    duree_ecoule = (date_valeur - date_dernier_coupon).days
    duree_ecoule_years = duree_ecoule / 365
    return duree_ecoule_years
    
def present_value(taux_nominal, taux_courbe, maturite_residuelle, nominal):
    # Règle le problème de maturité non entière. On calcule ici la valeur nette actuelle
    # en revenant à la date du dernier coupon : la maturité devient entière !
    print(taux_nominal)
    if not isinstance(taux_nominal, float):
        taux_nominal= float(taux_nominal.replace(',', '.'))
    taux_courbe=float(taux_courbe)

    print("TAUX NOM", taux_nominal)
    print("Taux Courbe", taux_courbe)
    # Si la maturité est décimale, on arrondit à l'entier supérieur pour le calcul.
    if int(maturite_residuelle) != maturite_residuelle:
        new_maturity = int(maturite_residuelle) + 1
    else:
        new_maturity = int(maturite_residuelle)

    # On calcule le coupon.
    coupon = taux_nominal * nominal

    # Création de la liste des coefficients d'actualisation pour chaque période.
    liste_coef = [1 / ((1 + taux_courbe) ** i) for i in range(1, new_maturity + 1)]
    print("COEFS", liste_coef)
    print("Coupon",coupon)
    # Calcul de la valeur actuelle du principal à maturité.
    present_value_principal = nominal / ((1 + taux_courbe) ** new_maturity)

    # Calcul de la valeur actuelle de chaque coupon.
    liste_coupon = [coupon * coef for coef in liste_coef]
    
    # Liste des flux de paiement, comprenant les coupons et le principal à maturité.
    liste_paiement = liste_coupon + [present_value_principal]

    # Somme des flux de paiement pour obtenir la valeur nette actuelle.
    return sum(liste_paiement)
    
def dirty_price(taux_nominal, taux_courbe, maturite_residuelle, nominal,date_valeur,date_emission):
    """
    Calcule le prix sale (dirty price) d'une obligation en tenant compte de la maturité résiduelle et des dates
    de valeur et d'émission.

    Arguments :
        taux_nominal (float) : Taux nominal de l'obligation (exprimé en pourcentage, par exemple 5.15 pour 5.15%)
        taux_courbe (float) : Taux issu de la courbe des taux (Yield to Maturity - YTM) utilisé pour actualiser les flux futurs
        maturite_residuelle (float) : Durée restante jusqu'à la maturité de l'obligation en années
        nominal (float) : Valeur nominale de l'obligation
        date_valeur (str) : Date de valeur de l'obligation au format "jj/mm/aaaa"
        date_emission (str) : Date d'émission de l'obligation au format "jj/mm/aaaa"

    Returns :
        dirty_price (float) : Le prix sale (dirty price) de l'obligation
    """
    # Calcul de la valeur nette actuelle de l'obligation
    PV = present_value(taux_nominal, taux_courbe, maturite_residuelle, nominal)

    # Vérifie si la maturité résiduelle est décimale
    if maturite_residuelle != int(maturite_residuelle):
        
        duree_ecoule_years=get_duree_dernier_coupon(date_valeur,date_emission)

        # Calcul du dirty price en utilisant la partie décimale de la maturité résiduelle
        dirty_price = PV * ((1 + taux_courbe) ** duree_ecoule_years)
        return dirty_price
    else:
        # Si la maturité résiduelle est entière, le dirty price est égal à la valeur nette actuelle
        return PV

    


def clean_price(taux_nominal, taux_courbe, maturite_residuelle, nominal,date_valeur,date_emission):
    # Calcul du dirty price en appelant la fonction dirty_price
    dirty = dirty_price(taux_nominal, taux_courbe, maturite_residuelle, nominal,date_valeur,date_emission)

    # Vérifie si la maturité résiduelle est décimale 
    if maturite_residuelle != int(maturite_residuelle):
        # Calcul du coupon
        coupon = nominal * taux_nominal

        duree_depuis_dernier_coupon=get_duree_dernier_coupon(date_valeur,date_emission)
        
        # Calcul des intérêts courus (pieds de coupon) en utilisant la partie décimale de la maturité résiduelle
        pieds_coupon = coupon * duree_depuis_dernier_coupon
        # Calcul du clean price en soustrayant les intérêts courus du dirty price
        clean_price = dirty - pieds_coupon

        return clean_price
    else:
        # Si la maturité résiduelle est entière, le clean price est égal au dirty price
        return dirty


# # Exemple d'utilisation 1 :
# taux_nominal_1 = 0.061  # 5.15%
# taux_courbe_1 = 0.03135 # 3.135%
# maturite_residuelle_1 = 1 - 0.284931507 # 0.284931507 ans
# nominal_1 = 100000
# date_emission_1 = "05/04/2004"
# date_valeur_1 = "18/07/2023"

# valeur_nette_actuelle_1 = present_value(taux_nominal_1, taux_courbe_1, maturite_residuelle_1, nominal_1)
# print("\033[1mExemple 1 - Maturité résiduelle < 1 an\033[0m")
# print("La valeur nette actuelle de l'obligation est de :", valeur_nette_actuelle_1)

# dirty_price_obligation_1 = dirty_price(taux_nominal_1, taux_courbe_1, maturite_residuelle_1, nominal_1, date_valeur_1, date_emission_1)
# print("Dirty Price de l'obligation 1 :", dirty_price_obligation_1)

# clean_price_obligation_1 = clean_price(taux_nominal_1, taux_courbe_1, maturite_residuelle_1, nominal_1, date_valeur_1, date_emission_1)
# print("Clean Price de l'obligation 1 :", clean_price_obligation_1)

# # Exemple d'utilisation 2 :
# taux_nominal_2 = 0.0515  # 5.15%
# taux_courbe_2 = 0.03669  # 3.669%
# maturite_residuelle_2 = 1053 / 365  #  ans (1053 jours correspondent à environ 2,880555556 ans)
# nominal_2 = 100000
# date_emission_2 = "05/06/2006"
# date_valeur_2 = "18/07/2023"
# date_echeance_2 = "05/06/2026"

# valeur_nette_actuelle_2 = present_value(taux_nominal_2, taux_courbe_2, maturite_residuelle_2, nominal_2)
# print("\033[1mExemple 2 - Maturité résiduelle > 1 an\033[0m")
# print("La valeur nette actuelle de l'obligation est de :", valeur_nette_actuelle_2)

# dirty_price_obligation_2 = dirty_price(taux_nominal_2, taux_courbe_2, maturite_residuelle_2, nominal_2, date_valeur_2, date_emission_2)
# print("Dirty Price de l'obligation 2 :", dirty_price_obligation_2)

# clean_price_obligation_2 = clean_price(taux_nominal_2, taux_courbe_2, maturite_residuelle_2, nominal_2, date_valeur_2, date_emission_2)
# print("Clean Price de l'obligation 2 :", clean_price_obligation_2)