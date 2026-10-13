import json, os, tempfile, unittest
from pipeline import classify, config as HC
from jev_lab import config as C, metrics as M, client as CL, store as ST, budget as B, runner as R, analysis as A, report as RP, mock, hemicycle as H


def _faux_scrutins():
    """data/ n'est pas versionné (CI) : titres officiels fictifs, un par fiche + des cas certains par construction."""
    d = {str(q["n"]): {"n": q["n"], "titre": f"l'ensemble de la proposition de loi n° {q['n']} visant à tester."} for q in H._fiches({"legacy", "pending_review", "published", "blocked"})}
    for i in range(1000, 1040):
        d[str(i)] = {"n": i, "titre": f"l'ensemble du projet de loi relatif au sujet {i}."}
        d[str(i + 1000)] = {"n": i + 1000, "titre": f"l'amendement n° {i} de suppression de l'article {i % 7 + 1}."}
    return d


if not os.path.exists(os.path.join(HC.DATA, "scrutins.json")):
    H.scrutins = _faux_scrutins


def rec(scenario, item, system="jev", group="", gold=None, answers=None, ok=True, experiment="quality", variant="base", rep=0, meta=None, text=None, cost=4.2e-6):
    """Un enregistrement du journal, tel que le client l'écrit."""
    r = {"experiment": experiment, "task": scenario, "scenario": scenario, "item": item, "group": group, "system": system, "model": "m", "variant": variant,
         "rep": rep, "gold": gold or {}, "meta": meta or {}, "ok": ok, "status": 200 if ok else 429, "wall_s": .1, "total_s": .1, "n_attempts": 1, "attempts": [],
         "usage": {"input_tokens": 100, "output_tokens": 10, "cost": cost}, "request": {"state": {"x": "y"}}}
    if ok and system == "jev":
        r["response"] = {"answers": answers or {}}
    if ok and system != "jev":
        r["text"] = text
    return r


def sens_rec(item, exact, accept_it, system="jev", **kw):
    """Un appel « sens du vote » : le bouton est exact ou inversé ; Jev l'accepte ou non."""
    ans = {"correspond": {"type": "noul", "noul": .95 if accept_it else .05}, "sens": {"type": "choice", "choice": "adopter" if accept_it else "supprimer", "confidence": .9, "probabilities": {}}}
    return rec("sens", item, system, group=("fiche:exact" if exact else "fiche:inverse"), gold={"q": {}, "accept": exact}, answers=ans,
               meta={"polarity_claimed": "adopt", "polarity_true": "adopt", "kind": "fiche"}, **kw)


class TestMetrics(unittest.TestCase):
    def test_percentile_auc_wilson(self):
        self.assertEqual(M.percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertEqual(M.auc([.9, .8, .2, .1], [1, 1, 0, 0]), 1.0)
        lo, hi = M.wilson(0, 60)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.06, delta=0.01)          # « zéro erreur sur 60 » laisse ≈ 6 % de borne haute

    def test_newcombe_zero_desaccord_reste_large_sur_peu_de_cas(self):
        d, lo, hi = M.newcombe_paired(0, 0, 0, 10)
        self.assertEqual(d, 0.0)
        self.assertLess(lo, -0.1)
        self.assertGreater(hi, 0.1)                            # le bootstrap aurait donné [0 ; 0]
        d, lo, hi = M.newcombe_paired(0, 0, 0, 400)
        self.assertLess(hi, 0.02)

    def test_mcnemar_holm_grappes(self):
        self.assertAlmostEqual(M.mcnemar_exact(3, 0), 0.25)
        self.assertAlmostEqual(M.holm([0.01, 0.04, 0.03])[0], 0.03)
        self.assertTrue(M.bootstrap_clusters([[1, 1], [2, 2], [3, 3], [4, 4]], M.mean)[0] <= 2.5)

    def test_calibration_et_macro_f1(self):
        ece, _ = M.calibration([0.9] * 10 + [0.5] * 10, [True] * 9 + [False] + [True] * 5 + [False] * 5)
        self.assertAlmostEqual(ece, 0.0)
        self.assertLess(M.macro_f1(["x", "ghost"], ["x", "x"]), M.macro_f1(["x", "x"], ["x", "x"]))


class TestHemicycle(unittest.TestCase):
    def test_les_questions_sont_celles_de_la_production(self):
        self.assertEqual(H.questions("pro_contre"), classify.pro_con_call({})[1])
        self.assertEqual(H.questions("neutralite"), classify.orientation_call({})[1])
        self.assertEqual(H.questions("categorie"), classify.category_call({})[1])
        self.assertEqual(H.questions("sens"), classify.direction_call("t", "x", "adopt")[1])

    def test_variantes_de_la_consigne_de_categorie(self):
        base, nd, sh = H.questions("categorie")["cat"], H.questions("categorie", "nodesc")["cat"], H.questions("categorie", "shuffle1")["cat"]
        self.assertEqual(set(base["criteria"]), set(sh["criteria"]))
        self.assertNotEqual(list(base["criteria"]), list(sh["criteria"]))
        self.assertTrue(all(k == v for k, v in nd["criteria"].items()))

    def test_jeu_d_essai_apparie_et_vrai_par_construction(self):
        its = H.items_sens()
        by = {}
        for i in its:
            by.setdefault(i["id"].rsplit("-", 1)[0], []).append(i)
        self.assertTrue(all(len(v) == 2 and {x["gold"]["accept"] for x in v} == {True, False} for v in by.values()))     # exact + inversé pour chaque vote
        pc = H.items_pro_contre()
        self.assertEqual({i["group"] for i in pc}, {"orig", "permutes", "contre_tronque", "contre_d_une_autre_mesure"})
        self.assertTrue(all(i["gold"]["accept"] == (i["group"] == "orig") for i in pc))

    def test_decision_identique_a_celle_de_la_production(self):
        a = {"correspond": {"type": "noul", "noul": .9}, "sens": {"type": "choice", "choice": "adopter", "confidence": .9}}
        item = {"gold": {}, "meta": {"polarity_claimed": "adopt"}}
        ok, det = classify.direction_verdict(a, "adopt")
        self.assertEqual(H.verdict("sens", item, a)["accept"], ok)
        a["correspond"]["noul"] = .5
        self.assertFalse(H.verdict("sens", item, a)["accept"])
        o = {"orientation": {"type": "score", "score": HC.NEUTRALITY_MAX + 0.5}, "bord": {"type": "choice", "choice": "aucun"}, "charge": {"type": "noul", "noul": .2}}
        self.assertFalse(H.verdict("neutralite", {"gold": {}, "meta": {}}, o)["accept"])
        o["orientation"]["score"] = HC.NEUTRALITY_MAX
        self.assertTrue(H.verdict("neutralite", {"gold": {}, "meta": {}}, o)["accept"])

    def test_normalisation_refuse_toute_reponse_incomplete(self):
        qs = H.questions("sens")
        self.assertIsNone(H.normalize(qs, {"correspond": {"noul": .9}}))                                    # question manquante
        self.assertIsNone(H.normalize(qs, {"correspond": {"noul": "abc"}, "sens": {"choice": "adopter"}}))  # valeur non numérique
        self.assertIsNone(H.normalize(qs, {"correspond": {"noul": .9}, "sens": {"choice": "n_importe_quoi"}}))
        self.assertIsNotNone(H.normalize(qs, {"correspond": {"noul": .9}, "sens": {"choice": " Adopter "}}))   # casse et espaces tolérés

    def test_lecture_de_la_reponse_d_un_modele_de_langage(self):
        qs = H.questions("sens")
        txt = 'Voici ma réponse {oui}.\n```json\n{"correspond": {"noul": 0.9}, "sens": {"choice": "adopter", "probabilities": {"adopter": 0.9}}}\n```'
        self.assertIsNotNone(H.chat_answers(qs, txt))
        self.assertIsNone(H.chat_answers(qs, "je ne sais pas"))


class TestAnalyse(unittest.TestCase):
    def test_echec_ferme_une_reponse_inexploitable_est_un_rejet(self):
        recs = [sens_rec(f"b{i}", False, False) for i in range(5)] + [rec("sens", "x", group="fiche:inverse", gold={"q": {}, "accept": False}, answers={}, meta={"polarity_claimed": "adopt"})]
        rows = A.tidy(recs)
        bad = [r for r in rows if r["gold"]["accept"] is False]
        self.assertEqual(sum(1 for r in bad if r["accept"]), 0)          # l'inexploitable n'est pas « accepté »
        self.assertEqual(sum(1 for r in bad if not r["valid"]), 1)
        good_failed = [rec("sens", "g", group="fiche:exact", gold={"q": {}, "accept": True}, ok=False, meta={"polarity_claimed": "adopt"})]
        rows = A.tidy(good_failed)
        self.assertFalse(rows[0]["accept"])                                # un appel échoué sur une bonne entrée = faux rejet

    def test_doublons_apres_reprise(self):
        recs = [sens_rec(f"g{i}", True, True) for i in range(10)] + [sens_rec("g3", True, True, ok=False), sens_rec("g3", True, True)]
        rows = A.tidy(recs)
        self.assertEqual(len(rows), 10)

    def test_far_frr_et_verdict_de_surete(self):
        recs = [sens_rec(f"e{i}", True, i >= 3) for i in range(60)] + [sens_rec(f"i{i}", False, i < 1) for i in range(60)]
        d = A.scenario_decision(A.tidy(recs), "sens")["jev"]
        self.assertEqual((d["frr"]["k"], d["frr"]["n"]), (3, 60))
        self.assertEqual((d["far"]["k"], d["far"]["n"]), (1, 60))
        sv = {(s["metric"]): s for s in A.safety_verdicts({"sens": {"jev": d}}, ) if s["scenario"] == "sens"}
        self.assertEqual(sv["far"]["label"], "inconclusif")      # 1/60 : borne basse sous 2 %, borne haute au-dessus
        self.assertEqual(sv["frr"]["label"], "respecté")

    def test_zero_erreur_sur_peu_de_cas_n_est_pas_respecte(self):
        recs = [sens_rec(f"i{i}", False, False) for i in range(60)] + [sens_rec(f"e{i}", True, True) for i in range(60)]
        d = A.scenario_decision(A.tidy(recs), "sens")["jev"]
        far = [s for s in A.safety_verdicts({"sens": {"jev": d}}) if s["metric"] == "far"][0]
        self.assertEqual(far["label"], "inconclusif")          # 0/60 → borne haute ≈ 6 % > 2 %

    def test_paire_jev_reference_zero_desaccord_sur_peu_de_cas_est_inconclusive(self):
        txt = json.dumps({"correspond": {"noul": .05}, "sens": {"choice": "supprimer", "probabilities": {}}})
        recs = []
        for i in range(10):
            recs += [sens_rec(f"i{i}", False, False), rec("sens", f"i{i}", "ref", group="fiche:inverse", gold={"q": {}, "accept": False}, text=txt, meta={"polarity_claimed": "adopt"})]
        p = [x for x in A.pairs(A.tidy(recs), "sens") if x["metric"] == "far"][0]
        self.assertEqual(p["label"], "inconclusif")

    def test_cout_par_fiche(self):
        recs = [rec(sc, f"i{i}", gold={"accept": True, "q": {}}, answers={}, cost=1e-5) for sc in H.ORDER for i in range(3)]
        c = A.cost(A.tidy(recs), {})
        self.assertAlmostEqual(c["par_fiche"]["jev"], 4e-5)


class TestClientEtStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["OPENROUTER_API_KEY"] = "cle-secrete-de-test"
        cls.srv, cls.S, cls.url = mock.start()
        cls.old = C.BASE
        C.set_base(cls.url)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        C.set_base(cls.old)

    def test_appel_jev_et_cle_jamais_journalisee(self):
        it = H.items_pro_contre()[0]
        r = CL.JevClient(mock_gold=True).call({"experiment": "t", "task": "pro_contre", "item": it["id"], "group": it["group"], "rep": 0, "variant": "base", "gold": it["gold"]},
                                              it["state"], H.questions("pro_contre"), gold=it["gold"]["q"])
        self.assertTrue(r["ok"])
        self.assertIsNotNone(H.normalize(H.questions("pro_contre"), r["response"]["answers"]))      # format lisible par le pipeline
        self.assertNotIn("cle-secrete-de-test", json.dumps(r))

    def test_reessai_429_et_400_sans_reessai(self):
        self.S.max_inflight = 0
        try:
            res = CL.http_json(C.JEV_URL, {"model": "m", "state": {}, "questions": {}}, attempts=3, sleep=lambda s: None)
        finally:
            self.S.max_inflight = 64
        self.assertEqual((res["ok"], len(res["attempts"])), (False, 3))
        big = {"model": "m", "state": {"x": "x" * 400000}, "questions": H.questions("categorie")}
        res = CL.http_json(C.JEV_URL, big, attempts=3, sleep=lambda s: None)
        self.assertEqual((res["status"], len(res["attempts"])), (400, 1))

    def test_connexion_persistante_et_reconnexion_transparente(self):
        body = {"model": "m", "state": {"x": "a"}, "questions": H.questions("categorie")}
        CL.http_json(C.JEV_URL, body)
        conn = list(CL._tls.pool.values())[0]
        CL.http_json(C.JEV_URL, body)
        self.assertIs(list(CL._tls.pool.values())[0], conn)
        conn.close()
        r = CL.http_json(C.JEV_URL, body)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["attempts"]), 1)

    def test_reponse_vide_ou_tronquee_est_un_echec_d_appel(self):
        for ch in ({"message": {"content": ""}, "finish_reason": "stop"}, {"message": {"content": '{"a":'}, "finish_reason": "length"}):
            old = CL.http_json
            CL.http_json = lambda *a, **k: {"ok": True, "status": 200, "wall_s": .1, "total_s": .1, "attempts": [], "headers": {}, "body": {"choices": [ch], "usage": {}}}
            try:
                r = CL.ChatClient("m").call({"experiment": "x", "task": "sens", "item": "1", "rep": 0, "variant": "base"}, "p")
            finally:
                CL.http_json = old
            self.assertFalse(r["ok"])
            self.assertIn("vide ou tronqué", r["error"])

    def test_store_cle_avec_modele_et_reprise(self):
        a = ST.rec_key({"experiment": "q", "task": "t", "item": "1", "system": "jev", "model": "typesafe/jev-1.13", "variant": "base", "rep": 0})
        b = ST.rec_key({"experiment": "q", "task": "t", "item": "1", "system": "jev", "model": "typesafe/jev-1.14", "variant": "base", "rep": 0})
        self.assertNotEqual(a, b)
        with tempfile.TemporaryDirectory() as d:
            st = ST.RunStore(d)
            st.append({"experiment": "q", "task": "t", "item": "1", "system": "jev", "variant": "base", "rep": 0, "ok": True})
            st.append({"experiment": "q", "task": "t", "item": "2", "system": "jev", "variant": "base", "rep": 0, "ok": False})
            self.assertEqual(len(ST.RunStore(d).done()), 1)
            with open(st.calls_path, encoding="utf-8") as fh:
                self.assertNotIn("Authorization", fh.read())

    def test_budget_cumule_et_reserve(self):
        b = B.Budget(1.0, spent0=0.9)
        with self.assertRaises(B.BudgetExceeded):
            b.acquire(0.2)
        b.acquire(0.05)
        with self.assertRaises(B.BudgetExceeded):
            b.acquire(0.06)
        b.release(0.05)
        b.acquire(0.06)


class TestChaineComplete(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["OPENROUTER_API_KEY"] = "cle-de-test"
        cls.srv, cls.S, cls.url = mock.start()
        cls.old = C.BASE
        C.set_base(cls.url)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        C.set_base(cls.old)

    def lab(self, d, budget=5.0):
        st = ST.RunStore(d)
        st.write_meta(mock=True, suite="smoke")
        return R.Lab(st, B.Budget(budget), CL.JevClient(mock_gold=True), [CL.ChatClient("anthropic/claude-haiku-5", label="claude-petit", mock_gold=True)], mock=True), st

    def test_qualite_reprise_et_rapport_complet(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d)
            jobs = lab.jobs_quality(["categorie", "sens"], cap=8)
            s1 = lab.execute(jobs, label="q")
            self.assertEqual((s1["run"], s1["failed"]), (len(jobs), 0))
            s2 = lab.execute(lab.jobs_quality(["categorie", "sens"], cap=8), label="q")
            self.assertEqual((s2["run"], s2["already_done"]), (0, len(jobs)))        # reprise : rien n'est rejoué
            rep = A.run(st)
            self.assertIn("jev", rep["categorie"])
            md = RP.build(rep, d)
            self.assertIn("DONNÉES SIMULÉES", md)
            with open(os.path.join(d, "summary.json"), encoding="utf-8") as fh:
                json.load(fh)

    def test_plafond_de_budget_arret_net(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d, budget=0.00002)
            stats = lab.execute(lab.jobs_quality(["sens"], cap=30), label="b")
            self.assertTrue(stats["budget_stop"])
            self.assertLess(lab.budget.spent, 0.00004)

    def test_plan_ne_depense_rien(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d)
            before = self.S.calls
            rows, total = lab.plan("smoke")
            self.assertGreater(total, 0)
            self.assertEqual(self.S.calls, before)

    def test_cout_non_rapporte_estime_pour_le_budget(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d)
            lab.prices["anthropic/claude-haiku-5"] = (1e-6, 5e-6)
            r = {"ok": True, "experiment": "x", "task": "sens", "item": "1", "variant": "base", "rep": 0, "system": "claude-petit", "usage": {"input_tokens": 1000, "output_tokens": 10, "cost": None}}
            job = R.Job({"experiment": "x", "task": "sens", "item": "1", "variant": "base", "rep": 0}, "claude-petit", 1000, 10, lambda: r)
            lab.execute([job], workers=1)
            self.assertAlmostEqual(lab.budget.spent, 1000 * 1e-6 + 10 * 5e-6)

    def test_les_variantes_de_neutralite_se_generent_et_se_relisent(self):
        q = H.fiches_pro_con()[0]
        r = CL.ChatClient("anthropic/claude-opus-5").call({"experiment": "gen", "task": "neutralite", "item": "g", "rep": 0, "variant": "pour", "gold": None}, H.variant_prompt(q, "pour"))
        v = H.json_in(r["text"])
        self.assertTrue(all(f in v for f in ("sum", "pro", "con")))
        items = H.items_neutralite({str(q["n"]): {"pour": v}})
        self.assertIn("pour", {i["group"] for i in items})

    def test_seuils_preenregistres_complets(self):
        for k in ("delta_non_inferiorite", "flip_max_determinisme", "tolerance_prix"):
            self.assertIn(k, C.PREREG)
        self.assertEqual(set(C.SAFETY), {"sens", "neutralite", "pro_contre"})


if __name__ == "__main__":
    unittest.main()
