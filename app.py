import streamlit as st
import pandas as pd
import numpy as np
import functools



# On ouvre la base de donnée teleadju et on la traite Elle va être utile 
# avec l'AMC pour trouver la date decheance donc la maturité resiudelle
# et donc les bornes entre lesquelles interpoller

# On ouvre la base de donnée de teleajdu une fois pour optimiser le temps de calcul
def open_amc_db(filepath):
    db=pd.read_excel(filepath)
    # Create a new column 'New Column' with the sliced characters
    db['AMC'] = db['Code ISIN'].str[5:11]
    # Create a mapping for renaming the columns
    column_mapping = {
        'Date Courbe': 'Date Courbe',
        'Code ISIN': 'Code ISIN',
        'Maturit&eacute;': 'Maturite',
        "Date d'&eacute;mission": "Date emission",
        "Date d'&eacute;ch&eacute;ance": "Date echeance",
        'Taux Nominal %': 'Taux Nominal %',
        'Valeur Nominale': 'Valeur Nominale',
        'Encours': 'Encours',
        'Taux Issu de la Courbe %': 'Taux Issu de la Courbe %',
        'Prix Pied de Coupon %': 'Prix Pied de Coupon %',
        'Coupon Couru Unitaire': 'Coupon Couru Unitaire',
        'Prix': 'Prix',
        'Applicable': 'Applicable',
        'AMC': 'AMC'
    }

    # Rename the columns using the mapping
    db.drop(columns=['Taux Nominal %', 'Valeur Nominale ', 'Encours',
                     'Taux Issu de la Courbe %', 'Prix Pied de Coupon %',
                     'Coupon Couru Unitaire', 'Prix', 'Applicable', 'Code ISIN', 'Date Courbe'], inplace=True)
    db.rename(columns=column_mapping, inplace=True)
    return db

# filepath='./TeleAdjudication (14).xls'
# amc_db=open_amc_db(filepath)
#amc_db.to_pickle('./TeleAdjudication.pkl')

amc_db= pd.read_pickle('./TeleAdjudication.pkl')

# On trouve l'échéance du bond avec son amc
def get_echeance(amc):
    amc=str(amc)
    line_of_interest=amc_db[amc_db['AMC']==amc]
    # Check if line_of_interest is empty before accessing the data
    if line_of_interest.empty:
        return None
    date_echeance = line_of_interest['Date echeance'].values[0]
    return date_echeance



# On trouve la maturité résiduelle d'un bond avec son amc

def get_maturite_residuellle(amc, date_valeur):
    date_echeance= get_echeance(amc)
    date_valeur = pd.to_datetime(date_valeur)  # Convert 'date_valeur' to datetime object
    date_echeance = pd.to_datetime(date_echeance)  # Convert 'date_echeance' to datetime object
    maturite_resid= date_echeance-date_valeur
    # Convert the timedelta to years
    maturite_resid_years = maturite_resid / pd.Timedelta(days=365.25)
    return maturite_resid_years


#Maintenant on ouvre la courbe lié à la DC voulue par le trader. Elle va 
# permettre d'obtenir le taux à la courbe à partir de la DV choisie


@functools.lru_cache(maxsize=128)  # Maxsize sets the number of function calls to cache
def get_courbe_data(date):
    
    # Format the date as DD%2FMM%2FYYYY
    formatted_date = date.strftime("%d%%2F%m%%2F%Y")

    # Construct the URL using the formatted date
    url = f"https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-obligataire/Marche-des-bons-de-tresor/Marche-secondaire/Taux-de-reference-des-bons-du-tresor?date={formatted_date}&block=e1d6b9bbf87f86f8ba53e8518e882982#address-c3367fcefc5f524397748201aee5dab8-e1d6b9bbf87f86f8ba53e8518e882982"

    # Read HTML tables from the URL
    dfs = pd.read_html(url)
    courbe_data=dfs[0]
    # Drop the last row because its not a date but total
    courbe_data.drop(courbe_data.index[-1], inplace=True)
    
    # Rename columns to match the desired names
    courbe_data.rename(columns={
            "Date d'échéance": 'Date echeance',
            'Date de la valeur': 'Date de la valeur',
            'Taux moyen pondéré': 'tmp',
            'Transaction': 'Transaction',
        }, inplace=True)

    
    # Convert the date columns to datetime objects
    courbe_data['Date echeance'] = pd.to_datetime(courbe_data['Date echeance'], format='%d/%m/%Y')
    courbe_data['Date de la valeur'] = pd.to_datetime(courbe_data['Date de la valeur'], format='%d/%m/%Y')
    
    # Convert the 'tmp' column to numeric (float) values and convert percentages to fractions
    courbe_data['tmp'] = courbe_data['tmp'].str.replace(',', '.').str.rstrip('%').astype(float) / 100

    return courbe_data

# Example usage:
date_input = pd.to_datetime("2023-07-20")
date_input= pd.to_datetime(date_input)
courbe_data = get_courbe_data(date_input)
print(courbe_data)

@functools.lru_cache(maxsize=128)  # Maxsize sets the number of function calls to cache
def get_taux_courbe(date_courbe, bond_maturation, date_valeur):
    courbe_data = get_courbe_data(date_courbe)

    # Convert the date columns to datetime objects
    courbe_data['Date echeance'] = pd.to_datetime(courbe_data['Date echeance'])
    courbe_data['Date de la valeur'] = pd.to_datetime(courbe_data['Date de la valeur'])

    # Add a column 'maturation' as the difference between the Date echeance and date_valeur in years
    courbe_data['maturation'] = (courbe_data['Date echeance'] - pd.to_datetime(date_valeur)).dt.days / 365.25

    # Sort the DataFrame by the 'maturation' column
    courbe_data = courbe_data.sort_values(by='maturation')

    # Calculate the slopes (rate of change) between consecutive maturities and corresponding interest rates
    courbe_data['slope'] = courbe_data['tmp'].diff() / courbe_data['maturation'].diff()

    # Find the two closest maturities that surround the bond_maturation
    lower_maturity = courbe_data[courbe_data['maturation'] <= bond_maturation]['maturation'].max()
    upper_maturity = courbe_data[courbe_data['maturation'] >= bond_maturation]['maturation'].min()

    if pd.isnull(lower_maturity):
        # Use the last calculated slope to project the new interest rate
        last_slope = courbe_data['slope'].iloc[-1]
        taux = courbe_data.loc[courbe_data['maturation'] == upper_maturity, 'tmp'].iloc[0] + last_slope * (bond_maturation - upper_maturity)
    elif pd.isnull(upper_maturity):
        # Use the first calculated slope to project the new interest rate
        first_slope = courbe_data['slope'].iloc[0]
        taux = courbe_data.loc[courbe_data['maturation'] == lower_maturity, 'tmp'].iloc[0] + first_slope * (bond_maturation - lower_maturity)
    else:
        # Interpolate the rate for the given bond_maturation as before
        lower_taux = courbe_data.loc[courbe_data['maturation'] == lower_maturity, 'tmp'].iloc[0]
        upper_taux = courbe_data.loc[courbe_data['maturation'] == upper_maturity, 'tmp'].iloc[0]
        taux = np.interp(bond_maturation, [lower_maturity, upper_maturity], [lower_taux, upper_taux])

    return taux

date_valo= pd.to_datetime("2025-07-20")
print(get_taux_courbe(date_input,5, date_valo))


# On passe à la partie trader, avant on ne regardait que le point de vue BAM.
# Avant les taux étaient donnés par BAM maintenant le trader va donner ses taux à partir des infos qu'ils récupèrent du marché auprès
# de son carnet d'adresse.
# A partir de ces taux on va interpoler le taux à donner pour le bon d'intérêt.

## On trouve les bornes entre lesquelles notre maturite se trouve 
 
@functools.lru_cache(maxsize=128)  # Maxsize sets the number of function calls to cache
def bornes_interpolation(maturite):
    # Define a list of specific bond maturities for interpolation
    common_maturities = [0.25, 0.5, 1, 2, 5, 10, 15, 20, 30]  # Years

    # Find the index of the largest common maturity that is smaller than the given bond maturity
    index = 0
    while index < len(common_maturities) and common_maturities[index] < maturite:
        index += 1

    # Determine the lower and upper bounds for interpolation
    lower_maturity = common_maturities[index - 1] if index > 0 else None
    upper_maturity = common_maturities[index] if index < len(common_maturities) else None

    return lower_maturity, upper_maturity

@functools.lru_cache(maxsize=9)  # Maxsize sets the number of function calls to cache
def hash_maturity_to_string(maturity):
    common_maturities = [0.25, 0.5, 1, 2, 5, 10, 15, 20, 30]
    maturity_strings = ["13 semaines", "26 semaines", "52 semaines","2 ans", "5 ans", "10 ans", "15 ans", "20 ans", "30 ans"]

    # Find the index of the maturity in the common_maturities list
    index = common_maturities.index(maturity) if maturity in common_maturities else -1

    # If the maturity is found in the list, return the associated string
    if index != -1:
        return maturity_strings[index]

    # If the maturity is not found, return a default string
    return "Unknown Maturity"

def get_maturite_days(maturite_years):
    # Calculate the maturite (remaining maturity) in days based on maturite_years
    days_per_year = 365.25  # Consider leap years
    if maturite_years==None:
        maturite_years=0
    return maturite_years * days_per_year

def get_rate_interpolation(bond_maturity,lower_maturity,upper_maturity,lower_rate,upper_rate):
    
    return np.interp(bond_maturity, [lower_maturity, upper_maturity], [lower_rate, upper_rate])


class SessionState:
    def __init__(self):
        self._state = {}

    def __getattr__(self, name):
        return self._state.get(name)

    def __setattr__(self, name, value):
        self._state[name] = value

    def clear(self):
        self._state.clear()


def main():
    # interpolated_rate=0

    # Titre en grand Pricer bons du trésor
    st.title("Pricer bons du trésor")

    # Champ d'entrée pour l'AMC
    amc = st.text_input("Entrez l'AMC de l'obligation")
    

    # Champ d'entrée pour la date de valorisation
    date_valeur = st.date_input("Sélectionnez la date de valorisation")

    # Champ d'entrée pour la date de courbe
    date_courbe = st.date_input("Sélectionnez la date de la courbe des taux")
    if amc:
        # Display the table header
        st.subheader("Table des bornes pour l'interpolation")
        bond_maturity=get_maturite_residuellle(amc,date_valeur)
        # Create the DataFrame for the table
        table_data = pd.DataFrame(columns=["Maturité (années)", "Maturité (jours)", "Taux(%)"])
        
        bond_maturity = get_maturite_residuellle(amc, date_valeur)
        lower_maturity, upper_maturity = bornes_interpolation(bond_maturity)

        # Calculate the days for bond_maturity and bounds
        bond_maturity_days = get_maturite_days(bond_maturity)
        lower_maturity_days = get_maturite_days(lower_maturity)
        upper_maturity_days = get_maturite_days(upper_maturity)
        
        lower_maturity_string= hash_maturity_to_string(lower_maturity)
        upper_maturity_string= hash_maturity_to_string(upper_maturity)
        
        lower_rate=None
        upper_rate= None
        interpolated_rate=None
        
        if not lower_rate:
        #     # Now update the DataFrame for the table with the new rate values
            table_data = table_data.append({"Maturité (années)": lower_maturity_string, "Maturité (jours)": lower_maturity_days, "Taux(%)": 0.0}, ignore_index=True)
            
        if not upper_rate and not interpolated_rate:

            table_data = table_data.append({"Maturité (années)": bond_maturity, "Maturité (jours)": bond_maturity_days, "Taux(%)": 0.0}, ignore_index=True)
            table_data = table_data.append({"Maturité (années)": upper_maturity_string, "Maturité (jours)": upper_maturity_days, "Taux(%)": 0.0}, ignore_index=True)


        # Use session_state to get the rate values
        lower_rate = st.number_input("Entrez le taux pour un "+ lower_maturity_string+"(Taux en %)", 
                            min_value=0.0,  # Set to None to leave it unrestricted
                            max_value=100.0,  # Set to None to leave it unrestricted
                            step=0.0001,  # Set the step increment
                            format="%.4f")  # Format the number to display 4 decimal places

        upper_rate = st.number_input("Entrez le taux pour un "+upper_maturity_string+"(Taux en %)", 
                            min_value=float(0),  # Set to None to leave it unrestricted
                            max_value=float(100),  # Set to None to leave it unrestricted
                            step=0.0001,  # Set the step increment
                            format="%.4f")  # Format the number to display 4 decimal places

        # Calculate and display the interpolated rate for the bond maturity
        if lower_rate:
            # Now update the DataFrame for the table with the new rate values
            table_data.loc[table_data['Maturité (années)'] == lower_maturity_string, 'Taux(%)'] = lower_rate
        if upper_rate:
            table_data.loc[table_data['Maturité (années)'] == upper_maturity_string, 'Taux(%)'] = upper_rate
            
        if lower_rate  and upper_rate :
            interpolated_rate = get_rate_interpolation(bond_maturity, lower_maturity, upper_maturity, lower_rate, upper_rate)
            # Now update the DataFrame for the table with the new rate values

            table_data.loc[table_data['Maturité (années)'] == bond_maturity, 'Taux(%)'] = interpolated_rate

        # Display the updated table
        st.table(table_data)

        if interpolated_rate:
            st.success(f"Le taux de RENDEMENT INTERPOLE : {interpolated_rate/100:.4%}")
            
            
    # Bouton pour valider les modifications
    if st.button("Calculer le taux à la courbe"):
        try:
            
            taux = get_taux_courbe(date_courbe, bond_maturity, date_valeur)
            st.success(f"Le taux de rendement de l'obligation à la COURBE est : {taux:.4%}")
        except Exception as e:
            st.error(f"Message d'erreur : {e}")




if __name__ == '__main__':
    main()
