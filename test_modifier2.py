import sys
import ssl
import json
import paho.mqtt.client as mqtt
import time
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt
from dotenv import load_dotenv
import os
import hashlib
import mysql.connector

load_dotenv()

# MQTT configuration
BROKER = "47567f9a74b445e6bef394abec5c83a1.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "ShellyPlusPlugS"
PASSWORD = "Ciel92110"

# Password hash from .env
STORED_HASH = os.getenv("STORED_HASH")

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="ciel",
        password="ciel",
        database="mon_projet"
    )

def verifier_mdp(mdp_saisi):
    mdp_hache = hashlib.sha256(mdp_saisi.encode()).hexdigest()
    return mdp_hache == STORED_HASH


class LoginPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Page de Connexion")
        self.setGeometry(100, 100, 400, 200)
        self.layout = QVBoxLayout()
        self.label = QLabel("Mot de passe :")
        self.layout.addWidget(self.label)
        self.mdp_input = QLineEdit()
        self.mdp_input.setEchoMode(QLineEdit.Password)
        self.layout.addWidget(self.mdp_input)
        self.connect_button = QPushButton("Se connecter")
        self.connect_button.clicked.connect(self.connexion)
        self.layout.addWidget(self.connect_button)
        self.setLayout(self.layout)

    def connexion(self):
        mdp_saisi = self.mdp_input.text().strip()
        if verifier_mdp(mdp_saisi):
            self.open_dashboard()
        else:
            print("Mot de passe incorrect")

    def open_dashboard(self):
        self.dashboard = Dashboard()
        self.dashboard.show()
        self.close()


class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard")
        self.setGeometry(100, 100, 1000, 500)

        self.layout = QVBoxLayout()
        self.add_button = QPushButton("Ajouter une prise Shelly")
        self.add_button.clicked.connect(self.ouvrir_formulaire)
        self.layout.addWidget(self.add_button)

        self.prises_layout = QHBoxLayout()
        self.scroll_content = QWidget()
        self.scroll_content.setLayout(self.prises_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(self.scroll_content)

        self.layout.addWidget(self.scroll_area)

        self.quit_button = QPushButton("Quitter l'application")
        self.quit_button.clicked.connect(self.close_application)
        self.layout.addWidget(self.quit_button)

        self.setLayout(self.layout)
        self.charger_prises_depuis_bdd()

    def ouvrir_formulaire(self):
        self.form_window = FormulaireWindow(self)
        self.form_window.show()

    def ajouter_prise(self, name, topic, localite):
        nouvelle_prise = ShellyWidget(name, topic, localite, self)
        self.prises_layout.addWidget(nouvelle_prise)
        self.scroll_content.adjustSize()

    def supprimer_prise(self, prise):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ids WHERE nom_prise = %s", (prise.name,))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"🗑️ Supprimé de la base : {prise.name}")
        except Exception as e:
            print(f"❌ Erreur suppression BDD : {e}")
        self.prises_layout.removeWidget(prise)
        prise.deleteLater()
        self.scroll_content.adjustSize()

    def charger_prises_depuis_bdd(self):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT valeur_id, nom_prise, localite FROM ids")
            for valeur_id, nom_prise, localite in cursor.fetchall():
                topic = f"shellyplusplugs-{valeur_id}/rpc"
                self.ajouter_prise(nom_prise, topic, localite)
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"❌ Erreur chargement BDD : {e}")

    def close_application(self):
        QApplication.quit()


class FormulaireWindow(QWidget):
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.setWindowTitle("Formulaire - Ajouter Prise Shelly")
        self.setGeometry(150, 150, 400, 200)

        layout = QVBoxLayout()
        self.name_label = QLabel("Nom de la prise Shelly :")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("ex: Prise Salon")

        self.id_label = QLabel("ID de la prise :")
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("ex: e465b8b41e28")

        self.localite_label = QLabel("Localité :")
        self.localite_input = QLineEdit()
        self.localite_input.setPlaceholderText("ex: L-334")

        self.create_button = QPushButton("Ajouter")
        self.create_button.clicked.connect(self.creer_prise_shelly)

        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.id_label)
        layout.addWidget(self.id_input)
        layout.addWidget(self.localite_label)
        layout.addWidget(self.localite_input)
        layout.addWidget(self.create_button)

        self.setLayout(layout)

    def creer_prise_shelly(self):
        name = self.name_input.text().strip()
        prise_id = self.id_input.text().strip()
        localite = self.localite_input.text().strip()
        topic = f"shellyplusplugs-{prise_id}/rpc"

        for i in range(self.dashboard.prises_layout.count()):
            widget = self.dashboard.prises_layout.itemAt(i).widget()
            if isinstance(widget, ShellyWidget):
                if widget.topic == topic or widget.name == name:
                    print("❌ ID ou nom déjà utilisé.")
                    return

        if name and prise_id and localite:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                query = "INSERT INTO ids (valeur_id, nom_prise, localite) VALUES (%s, %s, %s)"
                cursor.execute(query, (prise_id, name, localite))
                conn.commit()
                cursor.close()
                conn.close()
                print("✅ Enregistré en BDD")
            except Exception as e:
                print(f"❌ Erreur BDD : {e}")
                return

            self.dashboard.ajouter_prise(name, topic, localite)
            self.close()
        else:
            print("❌ Tous les champs sont obligatoires.")


class ShellyWidget(QFrame):
    def __init__(self, name, topic, localite, dashboard):
        super().__init__()
        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(2)

        self.name = name
        self.topic = topic
        self.localite = localite
        self.dashboard = dashboard

        self.layout = QVBoxLayout()

        self.image_label = QLabel()
        pixmap = QPixmap("prise2.png")
        pixmap = pixmap.scaled(120, 120)
        self.image_label.setPixmap(pixmap)
        self.layout.addWidget(self.image_label)

        self.name_label = QLabel(f"Nom : {name}")
        self.layout.addWidget(self.name_label)

        self.localite_label = QLabel(f"Localité : {localite}")
        self.layout.addWidget(self.localite_label)

        self.statut_label = QLabel("Statut : Inconnu")
        self.layout.addWidget(self.statut_label)

        self.power_label = QLabel("Puissance : -")
        self.layout.addWidget(self.power_label)

        self.conso_label = QLabel("Consommation : -")
        self.layout.addWidget(self.conso_label)

        self.on_button = QPushButton("Allumer")
        self.on_button.clicked.connect(self.allumer_prise)
        self.layout.addWidget(self.on_button)

        self.off_button = QPushButton("Éteindre")
        self.off_button.clicked.connect(self.eteindre_prise)
        self.layout.addWidget(self.off_button)

        self.delete_button = QPushButton("🗑️ Supprimer")
        self.delete_button.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.delete_button.clicked.connect(self.supprimer_prise)
        self.layout.addWidget(self.delete_button)

        self.edit_button = QPushButton("✏️ Modifier")
        self.edit_button.setStyleSheet("background-color: orange; color: white; font-weight: bold;")
        self.edit_button.clicked.connect(self.modifier_prise)
        self.layout.addWidget(self.edit_button)

        self.setLayout(self.layout)

        self.client = mqtt.Client(protocol=mqtt.MQTTv5)
        self.client.username_pw_set(USERNAME, PASSWORD)
        self.client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.init_mqtt()

        self.on_timestamp = None
        self.power_readings = []

    def init_mqtt(self):
        try:
            self.client.connect(BROKER, PORT, 60)
            self.client.loop_start()
        except Exception as e:
            self.statut_label.setText(f"❌ Connexion : {e}")

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.statut_label.setText("✅ Connecté")
            client.subscribe(self.topic)
            if not self.topic.endswith("/test"):
                client.subscribe(self.topic.replace("/rpc", "/test"))
            client.subscribe(self.topic.replace("/rpc", "/status"))
        else:
            self.statut_label.setText(f"❌ Connexion échouée (code {rc})")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload_str = msg.payload.decode("utf-8")
            data = json.loads(payload_str)

            if "status" in topic:
                etat = data.get("status")
                if etat == "on":
                    self.statut_label.setText("Statut : 🔴 Allumée")
                    self.image_label.setPixmap(QPixmap("prise4.png").scaled(120, 120))
                    self.on_button.setDisabled(True)
                    self.off_button.setDisabled(False)
                    self.on_timestamp = time.time()  # ⬅️ démarrage du comptage
                elif etat == "off":
                    self.statut_label.setText("Statut : 🟢 Éteinte")
                    self.image_label.setPixmap(QPixmap("prise3.png").scaled(120, 120))
                    self.on_button.setDisabled(False)
                    self.off_button.setDisabled(True)
                else:
                    self.statut_label.setText("Statut : ❓ Inconnu")
                return

            # Données de puissance
            power = data.get("apower", "N/A")
            self.power_label.setText(f"Puissance : {power} W")
            if isinstance(power, (int, float)):
                self.power_readings.append(power)

        except Exception as e:
            print(f"Erreur réception MQTT : {e}")

    def send_rpc_command(self, turn_on):
        message = {
            "id": 123,
            "src": "user_1",
            "method": "Switch.Set",
            "params": {"id": 0, "on": turn_on}
        }
        try:
            self.client.publish(self.topic, json.dumps(message), qos=1)
            print(f"📤 Commande envoyée : {message}")
        except Exception as e:
            print(f"❌ Erreur envoi commande : {e}")

    def allumer_prise(self):
        self.on_timestamp = time.time()
        self.power_readings = []
        self.send_rpc_command(True)

    def eteindre_prise(self):
        if self.on_timestamp:
            off_timestamp = time.time()
            duration_sec = int(off_timestamp - self.on_timestamp)

            if self.power_readings:
                average_power = sum(self.power_readings) / len(self.power_readings)
            else:
                average_power = 0

            print(f"🔋 Moyenne : {average_power:.2f} W sur {duration_sec} s")
            energy_watt_sec = average_power * duration_sec
            energy_kWh = energy_watt_sec / 3600000

            print(f"🔋 Énergie : {energy_kWh:.7f} kWh")

            self.conso_label.setText(
                f"Consommation : {energy_kWh:.7f} kWh"
            )

            self.power_readings = []

        self.send_rpc_command(False)

    def supprimer_prise(self):
        print(f"❌ Supprimer : {self.name}")
        self.send_rpc_command(False)
        self.client.loop_stop()
        self.client.disconnect()
        self.dashboard.supprimer_prise(self)

    def modifier_prise(self):
        self.edit_window = ModifierPriseWindow(self)
        self.edit_window.show()


class ModifierPriseWindow(QWidget):
    def __init__(self, shelly_widget):
        super().__init__()
        self.shelly_widget = shelly_widget
        self.setWindowTitle(f"Modifier - {self.shelly_widget.name}")
        self.setGeometry(200, 200, 400, 200)

        layout = QVBoxLayout()

        self.name_label = QLabel("Nouveau nom de la prise :")
        self.name_input = QLineEdit()
        self.name_input.setText(self.shelly_widget.name)

        self.localite_label = QLabel("Nouvelle localité :")
        self.localite_input = QLineEdit()
        self.localite_input.setText(self.shelly_widget.localite)

        self.save_button = QPushButton("Enregistrer les modifications")
        self.save_button.clicked.connect(self.sauvegarder_modifications)

        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.localite_label)
        layout.addWidget(self.localite_input)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

    def sauvegarder_modifications(self):
        nouveau_nom = self.name_input.text().strip()
        nouvelle_localite = self.localite_input.text().strip()

        if not nouveau_nom or not nouvelle_localite:
            print("❌ Tous les champs sont obligatoires.")
            return

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                UPDATE ids
                SET nom_prise = %s, localite = %s
                WHERE nom_prise = %s
            """
            cursor.execute(query, (nouveau_nom, nouvelle_localite, self.shelly_widget.name))
            conn.commit()
            cursor.close()
            conn.close()

            # Mise à jour dans l'interface
            self.shelly_widget.name = nouveau_nom
            self.shelly_widget.localite = nouvelle_localite
            self.shelly_widget.name_label.setText(f"Nom : {nouveau_nom}")
            self.shelly_widget.localite_label.setText(f"Localité : {nouvelle_localite}")
            print("✅ Prise modifiée avec succès.")
            self.close()
        except Exception as e:
            print(f"❌ Erreur lors de la modification : {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    login = LoginPage()
    login.show()
    sys.exit(app.exec())
