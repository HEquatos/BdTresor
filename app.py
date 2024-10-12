import streamlit as st
import pandas as pd
import numpy as np
import functools
from test import get_duree_dernier_coupon, present_value, dirty_price,clean_price
from corpusutils import open_amc_db, open_portfolio
from bs4 import BeautifulSoup
import bs4
# we want to ignore future depreciation warnings
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# On ouvre la base de donnée teleadju et on la traite Elle va être utile 
# avec l'AMC pour trouver la date decheance donc la maturité resiudelle
# et donc les bornes entre lesquelles interpoller


filepath_adju='./TeleAdjudication (14).xls'
amc_db=open_amc_db(filepath_adju)
# amc_db.to_pickle('./TeleAdjudication.pkl')

#plus facile d'ouvrir un pickle

#amc_db= pd.read_pickle('./TeleAdjudication.pkl')


### On ouvre le portfolio



#filepath_portfolio="./Input_Codexlsx.xlsx"
#portfolio= open_portfolio(filepath_portfolio)


# On trouve l'échéance du bond avec son amc
def get_echeance(amc):
    amc = str(amc)
    line_of_interest = amc_db[amc_db['AMC'] == amc]
    if line_of_interest.empty:
        raise ValueError(f"No bond found with AMC {amc}")
    return line_of_interest['Date echeance'].values[0]


def get_emission(amc):
    amc=str(amc)
    line_of_interest=amc_db[amc_db['AMC']==amc]
    date_emission = line_of_interest['Date emission'].values[0]
    return date_emission

def get_taux_nominal(amc):
    amc=str(amc)
    line_of_interest=amc_db[amc_db['AMC']==amc]
    buy_rate=line_of_interest['Taux Nominal %'].values[0]
    return buy_rate

# On trouve la maturité résiduelle d'un bond avec son amc

def get_maturite_residuellle(amc, date_valeur):
    date_echeance= get_echeance(amc)
    date_valeur = pd.to_datetime(date_valeur)  # Convert 'date_valeur' to datetime object
    date_echeance = pd.to_datetime(date_echeance)  # Convert 'date_echeance' to datetime object
    maturite_resid= date_echeance-date_valeur
    # Convert the timedelta to years
    maturite_resid_years = maturite_resid / pd.Timedelta(days=365.25)
    return maturite_resid_years

def get_maturite_days(maturite_years):
    # Calculate the maturite (remaining maturity) in days based on maturite_years
    days_per_year = 365.25  # Consider leap years
    if maturite_years==None:
        maturite_years=0
    return maturite_years * days_per_year

#Maintenant on ouvre la courbe lié à la DC voulue par le trader. Elle va 
# permettre d'obtenir le taux à la courbe à partir de la DV choisie

import pandas as pd
import requests
from io import StringIO
from urllib.parse import quote

def get_courbe_data(date):
    # Format the date as DD%2FMM%2FYYYY and URL-encode it
    formatted_date = date.strftime("%d/%m/%Y")
    encoded_date = quote(formatted_date, safe='')

    # Construct the URL for downloading the CSV
    url = f"https://www.bkam.ma/export/blockcsv/2340/c3367fcefc5f524397748201aee5dab8/e1d6b9bbf87f86f8ba53e8518e882982?date={encoded_date}&block=e1d6b9bbf87f86f8ba53e8518e882982"

    # Send a GET request to download the CSV
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    response = requests.get(url, headers=headers, verify=False)

    # Check if the response is successful
    if response.status_code == 200:
        # Load the CSV data into a DataFrame
        csv_data = StringIO(response.content.decode('utf-8'))
        courbe_data = pd.read_csv(csv_data, sep=';', skiprows=2)

        # Drop the last row because it contains the "Total"
        courbe_data.drop(courbe_data.tail(1).index, inplace=True)

        # Rename columns for better readability
        courbe_data.rename(columns={
            "Date d'échéance": 'Date echeance',
            'Date de la valeur': 'Date de la valeur',
            'Taux moyen pondéré': 'tmp',
            'Transaction': 'Transaction',
        }, inplace=True)

        # Convert the date columns to datetime objects
        courbe_data['Date echeance'] = pd.to_datetime(courbe_data['Date echeance'], format='%d/%m/%Y')
        courbe_data['Date de la valeur'] = pd.to_datetime(courbe_data['Date de la valeur'], format='%d/%m/%Y')

        # Clean the 'tmp' column (Taux moyen pondéré) and convert it to float
        courbe_data['tmp'] = courbe_data['tmp'].str.replace(',', '.').str.rstrip('%').astype(float) / 100

        return courbe_data

    else:
        print(f"Failed to download CSV. HTTP status code: {response.status_code}")
        return None


# # Example usage:
# date_input = pd.to_datetime("2023-07-20")
# date_input= pd.to_datetime(date_input)
# # courbe_data = get_courbe_data(date_input)
# # # print(courbe_data)

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

# date_valo= pd.to_datetime("2025-07-20")
# print(get_taux_courbe(date_input,5, date_valo))


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
    lower_maturity = common_maturities[index - 1] if index > 0 else 0
    upper_maturity = common_maturities[index] if index < len(common_maturities) else 0
    
    return lower_maturity, upper_maturity

@functools.lru_cache(maxsize=9)  # Maxsize sets the number of function calls to cache
def hash_maturity_to_string(maturity):
    common_maturities = [0, 0.25, 0.5, 1, 2, 5, 10, 15, 20, 30]
    maturity_strings = ["0 semaines","13 semaines", "26 semaines", "52 semaines","2 ans", "5 ans", "10 ans", "15 ans", "20 ans", "30 ans"]

    # Find the index of the maturity in the common_maturities list
    index = common_maturities.index(maturity) if maturity in common_maturities else -1

    # If the maturity is found in the list, return the associated string
    if index != -1:
        return maturity_strings[index]

    # If the maturity is not found, return a default string
    return "0 semaines"



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
    # Titre en grand Pricer bons du trésor
    st.title("Pricer bons du trésor")

    # Champ d'entrée pour l'AMC
    amc = st.text_input("Entrez l'AMC de l'obligation")

    # Champ d'entrée pour la date de valorisation
    date_valeur = st.date_input("Sélectionnez la date de valorisation")

    # Champ d'entrée pour la date de courbe
    date_courbe = st.date_input("Sélectionnez la date de la courbe des taux")

    if amc:
        bond_maturity = get_maturite_residuellle(amc, date_valeur)
        taux_nominal = get_taux_nominal(amc)
        date_echeance = get_echeance(amc)
        nominal = 100000
        date_emission = get_emission(amc)

        if not isinstance(taux_nominal, float):
            taux_nominal = float(taux_nominal.replace(',', '.'))

        try:
            taux_courbe = get_taux_courbe(date_courbe, bond_maturity, date_valeur)
            st.success(f"Le taux de rendement de l'obligation à la COURBE est : {taux_courbe:.4%}")
        except Exception as e:
            st.error(f"Message d'erreur : {e}")
            taux_courbe = None  # Ensure taux_courbe is set even if there's an error

        # Create the DataFrame for the table
        table_data = pd.DataFrame(columns=["Maturité (années)", "Maturité (jours)", "Taux(%)", "Description"])
        
        lower_maturity, upper_maturity = bornes_interpolation(bond_maturity)

        # Calculate the days for bond_maturity and bounds
        bond_maturity_days = get_maturite_days(bond_maturity)
        lower_maturity_days = get_maturite_days(lower_maturity)
        upper_maturity_days = get_maturite_days(upper_maturity)

        lower_maturity_string = hash_maturity_to_string(lower_maturity)
        upper_maturity_string = hash_maturity_to_string(upper_maturity)

        # Add rows to table_data (replacing append with pd.concat and handling string/numeric separation)
        new_row = pd.DataFrame([{
            "Maturité (années)": None,  # Using None for the string description, handled separately
            "Maturité (jours)": lower_maturity_days,
            "Taux(%)": 0.0,
            "Description": lower_maturity_string
        }])
        table_data = pd.concat([table_data, new_row], ignore_index=True)

        new_row = pd.DataFrame([{
            "Maturité (années)": bond_maturity,
            "Maturité (jours)": bond_maturity_days,
            "Taux(%)": 0.0,
            "Description": f"{bond_maturity:.2f} années"
        }])
        table_data = pd.concat([table_data, new_row], ignore_index=True)

        new_row = pd.DataFrame([{
            "Maturité (années)": None,
            "Maturité (jours)": upper_maturity_days,
            "Taux(%)": 0.0,
            "Description": upper_maturity_string
        }])
        table_data = pd.concat([table_data, new_row], ignore_index=True)

        # Use session_state to get the rate values
        lower_rate = st.number_input(f"Entrez le taux pour un {lower_maturity_string} (Taux en %)", 
                                     min_value=None, max_value=100.0, step=0.0001, format="%.4f")
        upper_rate = st.number_input(f"Entrez le taux pour un {upper_maturity_string} (Taux en %)", 
                                     min_value=None, max_value=100.0, step=0.0001, format="%.4f")

        # Update the DataFrame for the table with the new rate values
        if lower_rate is not None:
            table_data.loc[table_data['Description'] == lower_maturity_string, 'Taux(%)'] = lower_rate

        if upper_rate is not None:
            table_data.loc[table_data['Description'] == upper_maturity_string, 'Taux(%)'] = upper_rate

        interpolated_rate = None
        if lower_rate is not None and upper_rate is not None:
            interpolated_rate = get_rate_interpolation(bond_maturity, lower_maturity, upper_maturity, lower_rate, upper_rate)
            table_data.loc[table_data['Maturité (années)'] == bond_maturity, 'Taux(%)'] = interpolated_rate

        # Display the updated table
        st.table(table_data[['Description', 'Maturité (jours)', 'Taux(%)']])

        if interpolated_rate:
            st.success(f"TAUX DE RENDEMENT INTERPOLE : {interpolated_rate/100:.4%}")

        st.subheader("Pricing de l'obligation")

        # Select the rate for the trader
        if interpolated_rate is not None:
            taux_trader = st.number_input("Entrez le taux que vous voulez pour ce titre", value=interpolated_rate, step=0.001, format="%.3f")
        elif taux_courbe is not None:
            taux_trader = st.number_input("Entrez le taux que vous voulez pour ce titre", value=taux_courbe, step=0.001, format="%.3f")
        else:
            taux_trader = st.number_input("Entrez le taux que vous voulez pour ce titre", value=0.0, step=0.001, format="%.3f")

        taux_nominal_100 = taux_nominal / 100
        taux_trader_100 = taux_trader / 100

        # Calculate Present Value, Dirty Price, and Clean Price
        PV = present_value(taux_nominal_100, taux_trader_100, bond_maturity, nominal)
        st.success(f" Present Value : {PV} MAD")

        dirty = dirty_price(taux_nominal_100, taux_trader_100, bond_maturity, nominal, date_valeur, date_emission)
        st.success(f" Dirty Price : {dirty} MAD")

        clean = clean_price(taux_nominal_100, taux_trader_100, bond_maturity, nominal, date_valeur, date_emission)
        st.success(f" Clean Price : {clean} MAD")



        #quantity = 0
        #quantity=st.number_input("Combien échangez-vous?", value=0)



if __name__ == '__main__':
    main()
