import streamlit as st

def calcul(x):
    x=int(x)
    print("Voila")
    return x+4
    
def main():
    st.title('Taux de Bons du Trésor')

    # Champ d'entrée pour l'AMC
    amc = st.text_input('AMC (Acteur du Marché Central)')

    # Champ d'entrée pour la date de valorisation
    dv = st.date_input('Date de valorisation')

    # Champ d'entrée pour la date de maturation
    dc = st.date_input('Date de maturation (DC)')

    
    # Bouton pour valider les modifications
    if st.button('Valider'):
        # Ajoutez ici la logique pour traiter les données saisies et effectuer les calculs nécessaires
        test=calcul(amc)
        print(test)
        st.write(test)
        # Exemple : affichage des données saisies
        st.write('AMC:', amc)
        st.write('Date de valorisation:', dv)
        st.write('Date de maturation:', dc)

if __name__ == '__main__':
    main()
