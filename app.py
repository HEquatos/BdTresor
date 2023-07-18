import streamlit as st
import pandas as pd
import numpy as np
import http.client, urllib.request, urllib.parse, urllib.error, base64
import pandas as pd
import ast
import html5lib


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
    db.rename(columns=column_mapping, inplace=True)
    return db

filepath='./TeleAdjudication (14).xls'
amc_db=open_amc_db(filepath)
print(amc_db)

# On trouve l'échéance du bond avec son amc
def get_echeance(amc):
    amc=str(amc)
    line_of_interest=amc_db[amc_db['AMC']==amc]
    date_echeance = line_of_interest['Date echeance'].values[0]
    return date_echeance

# print(get_echeance(200709))

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
date_input = pd.to_datetime("2023-07-03")
date_input= pd.to_datetime(date_input)
courbe_data = get_courbe_data(date_input)
print(courbe_data)


def get_taux_courbe(date_courbe, bond_maturation, date_valeur):
    courbe_data = get_courbe_data(date_courbe)

    # Convert the date columns to datetime objects
    courbe_data['Date echeance'] = pd.to_datetime(courbe_data['Date echeance'])
    courbe_data['Date de la valeur'] = pd.to_datetime(courbe_data['Date de la valeur'])

    # Add a column 'maturation' as the difference between the Date echeance and date_valeur in years
    courbe_data['maturation'] = (courbe_data['Date echeance'] - pd.to_datetime(date_valeur)).dt.days / 365.25
    print(courbe_data)
    # Sort the DataFrame by the 'maturation' column
    courbe_data = courbe_data.sort_values(by='maturation')
    # print(courbe_data)
    # Find the two closest maturities that surround the bond_maturation
    lower_maturity = courbe_data[courbe_data['maturation'] <= bond_maturation]['maturation'].max()
    upper_maturity = courbe_data[courbe_data['maturation'] >= bond_maturation]['maturation'].min()
    print(lower_maturity,upper_maturity)
    # If bond_maturation is outside the range, use the closest maturity
    if pd.isnull(lower_maturity):
        taux = courbe_data.loc[courbe_data['maturation'] == upper_maturity, 'tmp'].iloc[0]
    elif pd.isnull(upper_maturity):
        taux = courbe_data.loc[courbe_data['maturation'] == lower_maturity, 'tmp'].iloc[0]
    else:
        # Interpolate the rate for the given bond_maturation
        lower_taux = courbe_data.loc[courbe_data['maturation'] == lower_maturity, 'tmp'].iloc[0]
        upper_taux = courbe_data.loc[courbe_data['maturation'] == upper_maturity, 'tmp'].iloc[0]
        taux = np.interp(bond_maturation, [lower_maturity, upper_maturity], [lower_taux, upper_taux])

    return taux


print(get_taux_courbe(date_input,5, date_input))

def main():
    # Titre en grand Pricer bons du trésor
    st.title("Pricer bons du trésor")

    # Champ d'entrée pour l'AMC
    amc = st.text_input("Entrez l'AMC de l'obligation")

    # Champ d'entrée pour la date de valorisation
    date_valeur = st.date_input("Sélectionnez la date de valorisation")

    # Champ d'entrée pour la date de courbe
    date_courbe = st.date_input("Sélectionnez la date de la courbe des taux")

    # Bouton pour valider les modifications
    if st.button("Calculer le rendement"):
        try:
            bond_maturation = get_maturite_residuellle(amc, date_valeur)
            taux = get_taux_courbe(date_courbe, bond_maturation, date_valeur)
            st.success(f"Le taux de rendement de l'obligation à la courbe est : {taux:.4%}")
        except Exception as e:
            st.error("Une erreur s'est produite lors du calcul du taux.")
            st.error(f"Message d'erreur : {e}")

if __name__ == '__main__':
    main()
