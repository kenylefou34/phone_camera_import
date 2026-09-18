"""Limitation des essais d'authentification (issue #19).

Pourquoi ce n'est pas qu'une question de mot de passe : chaque vérification
coûte ~100 ms de calcul AU SERVEUR (PBKDF2, 240 000 itérations, adminauth).
Sans limite, quelques dizaines de requêtes simultanées occupent les deux cœurs
du NUC à calculer des empreintes — et le tri des médias tourne dans le même
processus, derrière un verrou. Saturer l'authentification, c'est ralentir
l'import, sans même connaître un seul mot de passe valide.

L'horloge est injectée partout : aucun test ne dort.
"""

from phototheque import essais


def test_les_premiers_essais_ne_coutent_aucune_attente():
    """Une faute de frappe ne doit rien déclencher du tout."""
    limiteur = essais.Limiteur(seuil=5)
    for i in range(5):
        assert limiteur.doit_attendre("192.168.1.50", maintenant=i) == 0
        limiteur.echec("192.168.1.50", maintenant=i)


def test_au_dela_du_seuil_une_attente_est_imposee():
    limiteur = essais.Limiteur(seuil=3, delai_base=2)
    for i in range(3):
        limiteur.echec("192.168.1.50", maintenant=0)
    assert limiteur.doit_attendre("192.168.1.50", maintenant=0) > 0


def test_l_attente_double_a_chaque_nouvel_echec():
    """Doubler rend l'acharnement vite intenable, sans punir la maladresse."""
    limiteur = essais.Limiteur(seuil=1, delai_base=2, delai_max=1000)
    attentes = []
    t = 0
    for _ in range(4):
        limiteur.echec("192.168.1.50", maintenant=t)
        attentes.append(limiteur.doit_attendre("192.168.1.50", maintenant=t))
        t += 1000            # on laisse passer l'attente avant l'essai suivant
    assert attentes == sorted(attentes), attentes
    assert attentes[-1] >= attentes[0] * 4, attentes


def test_l_attente_est_plafonnee():
    """Sans plafond, une nuit d'essais fermerait l'administration pour des jours.

    C'est le mainteneur que ça punirait : l'attaquant, lui, est déjà parti.
    """
    limiteur = essais.Limiteur(seuil=1, delai_base=2, delai_max=60)
    t = 0
    for _ in range(30):
        t += 100_000
        limiteur.echec("192.168.1.50", maintenant=t)
    # Mesuré À L'INSTANT du dernier échec : quelques secondes plus tard
    # l'attente serait écoulée et le test passerait sans rien vérifier.
    attente = limiteur.doit_attendre("192.168.1.50", maintenant=t)
    assert 0 < attente <= 60, attente


def test_l_attente_s_ecoule_avec_le_temps():
    limiteur = essais.Limiteur(seuil=1, delai_base=10)
    limiteur.echec("192.168.1.50", maintenant=0)
    assert limiteur.doit_attendre("192.168.1.50", maintenant=0) > 0
    assert limiteur.doit_attendre("192.168.1.50", maintenant=999) == 0


def test_une_reussite_efface_l_ardoise():
    """Sinon le mainteneur traînerait ses erreurs de la veille."""
    limiteur = essais.Limiteur(seuil=1, delai_base=10)
    limiteur.echec("192.168.1.50", maintenant=0)
    limiteur.succes("192.168.1.50")
    assert limiteur.doit_attendre("192.168.1.50", maintenant=0) == 0


def test_deux_machines_sont_comptees_separement():
    """Sinon n'importe qui sur le réseau pourrait fermer l'admin au mainteneur.

    Ce serait un déni de service offert à l'attaquant : quelques essais ratés
    depuis un appareil quelconque, et le mainteneur ne peut plus entrer.
    """
    limiteur = essais.Limiteur(seuil=1, delai_base=10)
    for _ in range(5):
        limiteur.echec("192.168.1.99", maintenant=0)
    assert limiteur.doit_attendre("192.168.1.99", maintenant=0) > 0
    assert limiteur.doit_attendre("192.168.1.50", maintenant=0) == 0


def test_la_table_des_sources_ne_grossit_pas_sans_fin():
    """Mémoriser une ligne par adresse vue est une fuite de mémoire offerte.

    Le NUC n'a que 3 Gio : une table sans borne serait un second moyen de le
    faire tomber, à la place de celui qu'on vient de fermer.
    """
    limiteur = essais.Limiteur(seuil=1, max_sources=50)
    for i in range(500):
        limiteur.echec(f"10.0.{i // 256}.{i % 256}", maintenant=i)
    assert len(limiteur) <= 50, len(limiteur)


def test_la_source_la_plus_recente_survit_au_menage():
    """Le ménage ne doit pas offrir l'ardoise blanche à qui martèle le service."""
    limiteur = essais.Limiteur(seuil=1, delai_base=10, max_sources=10)
    for i in range(100):
        limiteur.echec("10.0.0.1", maintenant=i)          # l'acharné
        limiteur.echec(f"10.9.{i // 256}.{i % 256}", maintenant=i)
    assert limiteur.doit_attendre("10.0.0.1", maintenant=100) > 0


def test_la_premiere_attente_vaut_exactement_le_delai_de_base():
    """Décalage d'un cran facile à commettre, et invisible sans cette mesure.

    Constaté sur une démonstration réelle : le premier refus annonçait
    « Retry-After: 1 » alors que le délai de base valait 2 secondes. La suite
    doublait bien, donc les tests de croissance passaient — seul l'affichage
    de la toute première attente trahissait l'écart.
    """
    limiteur = essais.Limiteur(seuil=3, delai_base=2, delai_max=1000)
    for _ in range(3):
        limiteur.echec("192.168.1.50", maintenant=0)
    assert limiteur.doit_attendre("192.168.1.50", maintenant=0) == 2
