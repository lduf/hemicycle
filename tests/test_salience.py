import unittest
from pipeline import salience as S, salience_study as ST

CR = b"""<?xml version='1.0' encoding='UTF-8'?>
<compteRendu xmlns="http://schemas.assemblee-nationale.fr/referentiel"><seanceRef>RU1</seanceRef><contenu>
<point nivpoint="1"><orateurs/><texte>Droit &#224; l'aide &#224; mourir</texte>
 <paragraphe id_acteur="PA1" roledebat="president"><orateurs/><texte stime="10.0">La parole est &#224; M. X.</texte></paragraphe>
 <paragraphe id_acteur="PA2"><orateurs/><texte stime="20.0">Une phrase de quatre mots.</texte></paragraphe>
 <paragraphe id_acteur="PA3"><orateurs/><texte stime="80.0">Autre</texte></paragraphe>
</point>
<point nivpoint="1"><orateurs/><texte>Questions au Gouvernement</texte>
 <paragraphe id_acteur="PA2"><orateurs/><texte stime="100.0">Question</texte></paragraphe>
</point></contenu></compteRendu>"""


class TestSalience(unittest.TestCase):
    def test_overlap_ignore_mots_vides_et_accents(self):
        self.assertGreaterEqual(S.overlap("Mayotte : refondation", "Projet de loi de programmation pour la refondation de Mayotte"), 1.0)
        self.assertEqual(S.overlap("Questions au Gouvernement", "Projet de loi de finances"), 0.0)

    def test_parse_compte_rendu_compte_orateurs_et_duree(self):
        ref, pts = S.parse_compte_rendu(CR)
        self.assertEqual(ref, "RU1")
        self.assertEqual(len(pts), 2)
        p = pts[0]
        self.assertEqual(p["orateurs"], {"PA2", "PA3"})  # le président n'est pas compté
        self.assertEqual(p["interventions"], 2)
        self.assertEqual((p["t0"], p["t1"]), (10.0, 80.0))

    def test_attribute_titre_court_vs_titre_officiel(self):
        _, pts = S.parse_compte_rendu(CR)
        cands = [("Proposition de loi relative au droit à l'aide à mourir", "DL1"), ("Questions au Gouvernement", None)]
        res = S.attribute(pts, cands)
        self.assertEqual([r for _, r in res], ["DL1", None])

    def test_attribute_repli_un_seul_dossier(self):
        pts = [{"titre": "Fin des travaux", "orateurs": {"a"}, "interventions": 1, "mots": 1, "t0": 0, "t1": 1}]
        self.assertEqual(S.attribute(pts, [("Texte sans rapport lexical", "DL9")])[0][1], "DL9")
        pts[0]["titre"] = "Questions au gouvernement"
        self.assertIsNone(S.attribute(pts, [("Texte sans rapport lexical", "DL9")])[0][1])

    def test_pct_rank_et_composite(self):
        self.assertEqual(S.pct_rank([5, 1, 3]), [1.0, 0.0, 0.5])
        self.assertEqual(S.pct_rank([1, 1, 2]), [0.25, 0.25, 1.0])
        rows = {"a": {"x": 1, "y": 9}, "b": {"x": 5, "y": 5}, "c": {"x": 9, "y": 1}}
        c = S.composite(rows, ["x", "y"])
        self.assertEqual(c["a"], c["c"])  # les rangs se compensent

    def test_link_scrutins_trois_voies(self):
        scr = {1: ("DL1", "SPO", "x", "S1"), 2: (None, "SPO", "x", "S1"), 3: (None, "SPS", "l'ensemble de la proposition de loi visant à sortir du narcotrafic", "S2")}
        dos = {"DL2": {"votes": [2]}}
        odj = {"S2": [("Discussion de la proposition de loi visant à sortir du narcotrafic", "DL3")]}
        out = S.link_scrutins(scr, odj, dos)
        self.assertEqual(out, {1: ("DL1", "scrutin"), 2: ("DL2", "dossier"), 3: ("DL3", "ordre du jour")})


class TestEtude(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(ST.auc([3, 4], [1, 2]), 1.0)
        self.assertEqual(ST.auc([1, 2], [3, 4]), 0.0)
        self.assertEqual(ST.auc([1], [1]), 0.5)

    def test_kind_utilise_la_procedure(self):
        self.assertEqual(ST.kind({"titre": "Accorder le versement des allocations", "procedure": "Proposition de loi ordinaire"}), "proposition de loi")
        self.assertEqual(ST.kind({"titre": "Dénoncer les accords franco-algériens", "procedure": "Résolution"}), "résolution")
        self.assertEqual(ST.kind({"titre": "Projet de loi de finances pour 2026", "procedure": "Projet de loi ordinaire"}), "budget")

    def test_non_legislatif(self):
        self.assertFalse(ST.legislatif({"titre": "Motion de censure déposée", "procedure": "Proposition de loi ordinaire"}))
        self.assertFalse(ST.legislatif({"titre": "x", "procedure": "Engagement de la responsabilité gouvernementale"}))
        self.assertTrue(ST.legislatif({"titre": "Fin de vie", "procedure": "Proposition de loi ordinaire"}))


if __name__ == "__main__":
    unittest.main()
