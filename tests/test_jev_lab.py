import json, os, tempfile, unittest
from jev_lab import config as C, metrics as M, tasks as T, synth as SY, client as CL, store as ST, budget as B, runner as R, analysis as A, report as RP, mock


class TestMetrics(unittest.TestCase):
    def test_percentile_et_auc(self):
        self.assertEqual(M.percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(M.percentile([0, 10], 25), 2.5)
        self.assertEqual(M.auc([.9, .8, .2, .1], [1, 1, 0, 0]), 1.0)
        self.assertEqual(M.auc([.1, .2, .8, .9], [1, 1, 0, 0]), 0.0)
        self.assertEqual(M.auc([.5, .5], [1, 0]), 0.5)

    def test_mcnemar_et_holm(self):
        self.assertAlmostEqual(M.mcnemar_exact(3, 0), 0.25)
        self.assertEqual(M.mcnemar_exact(0, 0), 1.0)
        adj = M.holm([0.01, 0.04, 0.03])
        self.assertAlmostEqual(adj[0], 0.03)
        self.assertTrue(all(a >= p for a, p in zip(adj, [0.01, 0.04, 0.03])))

    def test_calibration_parfaite_et_abstention(self):
        conf = [0.9] * 10 + [0.5] * 10
        correct = [True] * 9 + [False] + [True] * 5 + [False] * 5
        ece, bins = M.calibration(conf, correct)
        self.assertAlmostEqual(ece, 0.0)
        rc = M.risk_coverage(conf, correct, covs=(0.5, 1.0))
        self.assertAlmostEqual(rc[0.5], 0.9)
        self.assertAlmostEqual(rc[1.0], 0.7)

    def test_bootstrap_ci_encadre_la_moyenne(self):
        lo, hi = M.bootstrap_ci([1.0] * 80 + [0.0] * 20)
        self.assertLess(lo, 0.8)
        self.assertGreater(hi, 0.8)

    def test_seuil_deux_moities_evite_la_fuite(self):
        p = [i / 100 for i in range(100)]
        y = [x > .5 for x in p]
        bal, ts = M.threshold_two_fold(p, y)
        self.assertGreater(bal, 0.9)


class TestTasks(unittest.TestCase):
    def test_specs_conformes_a_la_doc(self):
        t = T.TASKS["ag_news"]
        sp = T.spec(t)
        self.assertEqual(sp["type"], "choice")
        self.assertIsInstance(sp["criteria"], dict)            # {option: description}, comme dans le tutoriel officiel
        n = T.spec(T.TASKS["sst2"])
        self.assertEqual(set(n["criteria"]), {"true", "false"})
        s = T.spec(T.TASKS["sst5"])
        self.assertEqual(len(s["criteria"]), 5)

    def test_permutation_ne_perd_aucune_option(self):
        a, b = T.spec(T.TASKS["ag_news"]), T.spec(T.TASKS["ag_news"], "shuffle1")
        self.assertEqual(set(a["criteria"]), set(b["criteria"]))
        self.assertNotEqual(list(a["criteria"]), list(b["criteria"]))

    def test_prompt_chat_contient_memes_libelles(self):
        t = T.TASKS["ag_news"]
        pr = T.chat_prompt(t, {"article": "x"})
        for k in t.options:
            self.assertIn(k, pr)

    def test_parse_jev_trois_primitives(self):
        c = T.parse_jev(T.TASKS["ag_news"], {"type": "choice", "choice": "sports", "confidence": .9, "probabilities": {"sports": .9}})
        self.assertEqual((c["pred"], c["conf"]), ("sports", .9))
        self.assertIsNone(T.parse_jev(T.TASKS["ag_news"], {"choice": "inconnu"})["pred"])
        n = T.parse_jev(T.TASKS["sst2"], {"noul": .96})
        self.assertEqual((n["pred"], n["p_yes"]), (True, .96))
        s = T.parse_jev(T.TASKS["sst5"], {"score": 1.99, "confidence": .9, "probabilities": {"0": 0, "1": .1, "2": .9}})
        self.assertEqual(s["pred"], 2)

    def test_parse_chat_tolere_le_bruit_markdown(self):
        r = T.parse_chat(T.TASKS["ag_news"], 'Voici :\n```json\n{"choice": "world", "confidence": 0.7}\n```')
        self.assertEqual(r["pred"], "world")
        self.assertIsNone(T.parse_chat(T.TASKS["ag_news"], "je ne sais pas")["pred"])
        self.assertIsNone(T.parse_chat(T.TASKS["sst5"], '{"level": 9}')["pred"])


class TestCustom(unittest.TestCase):
    def test_tache_personnalisee(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"task": "perso", "primitive": "choice", "instructions": "Qui ?", "options": {"a": "A", "b": "B"}}) + "\n")
                fh.write(json.dumps({"state": {"txt": "x"}, "gold": "a"}) + "\n" + json.dumps({"state": {"txt": "y"}, "gold": "b"}) + "\n")
            t = T.load_custom(path)
            self.assertEqual((t.id, t.primitive, len(T.CUSTOM_ITEMS["perso"])), ("perso", "choice", 2))
            self.assertEqual(T.CUSTOM_ITEMS["perso"][0]["id"], "perso-0")
            self.assertEqual(T.spec(t)["criteria"], {"a": "A", "b": "B"})


class TestSynth(unittest.TestCase):
    def test_verite_calculee_par_le_programme(self):
        for it in SY.gen_counting(30, 1):
            self.assertEqual(it["state"]["texte"].split().count("chat"), int(it["gold"]))
        for it in SY.gen_arith(30, 1):
            s = it["state"]
            self.assertEqual(it["gold"], s["a"] + s["b"] > s["seuil"])
        for it in SY.gen_max(30, 1):
            n = it["state"]["nombres"]
            self.assertEqual(n.index(max(n)), "abcd".index(it["gold"]))

    def test_bruit_ajoute_la_taille_demandee(self):
        t = T.TASKS["ag_news"]
        st = SY.add_noise(t, {"article": "court"}, 600, "before", 1)
        self.assertGreater(len(st["article"]), 600 * 3)
        self.assertTrue(st["article"].endswith("court"))


class TestClientEtStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["JEVLAB_FIXTURES"] = "1"
        os.environ["OPENROUTER_API_KEY"] = "cle-secrete-de-test"
        cls.srv, cls.S, cls.url = mock.start()
        cls.old = C.BASE
        C.set_base(cls.url)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        C.set_base(cls.old)
        os.environ.pop("JEVLAB_FIXTURES", None)

    def test_appel_jev_complet_et_cle_jamais_journalisee(self):
        rec = CL.JevClient(mock_gold=True).call({"experiment": "t", "task": "ag_news", "item": "x", "rep": 0, "variant": "base", "gold": "sports"},
                                                {"article": "a"}, {"q": T.spec(T.TASKS["ag_news"])}, gold={"q": "sports"})
        self.assertTrue(rec["ok"])
        self.assertIn("cost", rec["usage"])
        self.assertNotIn("cle-secrete-de-test", json.dumps(rec))

    def test_reessai_sur_429_compte_les_tentatives(self):
        self.S.max_inflight = 0          # tout est refusé
        try:
            res = CL.http_json(C.JEV_URL, {"model": "m", "state": {}, "questions": {}}, attempts=3, sleep=lambda s: None)
        finally:
            self.S.max_inflight = 64
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["attempts"]), 3)
        self.assertTrue(all(a["status"] == 429 for a in res["attempts"]))

    def test_400_pas_de_reessai(self):
        t = T.TASKS["ag_news"]
        big = {"article": "x" * 400000}
        res = CL.http_json(C.JEV_URL, {"model": "m", "state": big, "questions": {"q": T.spec(t)}}, attempts=3, sleep=lambda s: None)
        self.assertFalse(res["ok"])
        self.assertEqual((res["status"], len(res["attempts"])), (400, 1))

    def test_store_reprise_et_pas_de_cle(self):
        with tempfile.TemporaryDirectory() as d:
            st = ST.RunStore(d)
            st.append({"experiment": "q", "task": "a", "item": "1", "system": "jev", "variant": "base", "rep": 0, "ok": True})
            st.append({"experiment": "q", "task": "a", "item": "2", "system": "jev", "variant": "base", "rep": 0, "ok": False})
            self.assertEqual(len(ST.RunStore(d).done()), 1)       # l'échec sera rejoué à la reprise
            with open(st.calls_path, encoding="utf-8") as fh:
                self.assertNotIn("Authorization", fh.read())


class TestChaineComplete(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["JEVLAB_FIXTURES"] = "1"
        os.environ["OPENROUTER_API_KEY"] = "cle-de-test"
        cls.srv, cls.S, cls.url = mock.start(jev_acc=0.9, chat_acc={"default": 0.9})
        cls.old = C.BASE
        C.set_base(cls.url)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        C.set_base(cls.old)
        os.environ.pop("JEVLAB_FIXTURES", None)

    def lab(self, d, budget=5.0):
        st = ST.RunStore(d)
        st.write_meta(mock=True, suite="smoke")
        return R.Lab(st, B.Budget(budget), CL.JevClient(mock_gold=True), [CL.ChatClient("anthropic/claude-haiku-5", mock_gold=True)], mock=True), st

    def test_qualite_reprise_et_rapport(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d)
            jobs = lab.jobs_quality(["ag_news", "sst2"], 12, 12)
            s1 = lab.execute(jobs, label="q")
            self.assertEqual((s1["run"], s1["failed"]), (len(jobs), 0))
            s2 = lab.execute(lab.jobs_quality(["ag_news", "sst2"], 12, 12), label="q")
            self.assertEqual((s2["run"], s2["already_done"]), (0, len(jobs)))       # reprise : rien n'est rejoué
            rep = A.run(st)
            self.assertIn(("ag_news", "jev"), rep["quality"]["cells"])
            md = RP.build(rep, d)
            self.assertIn("DONNÉES SIMULÉES", md)
            with open(os.path.join(d, "summary.json"), encoding="utf-8") as fh:
                json.load(fh)

    def test_plafond_de_budget_arret_net(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d, budget=0.00002)
            stats = lab.execute(lab.jobs_quality(["ag_news"], 30, 30), label="b")
            self.assertTrue(stats["budget_stop"])
            self.assertLess(lab.budget.spent, 0.00004)

    def test_cout_non_rapporte_est_estime_pour_le_budget(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d)
            lab.prices["anthropic/claude-haiku-5"] = (1e-6, 5e-6)
            name = lab.baselines[0].name
            rec = {"ok": True, "experiment": "x", "task": "ag_news", "item": "1", "variant": "base", "rep": 0, "system": name,
                   "usage": {"input_tokens": 1000, "output_tokens": 10, "cost": None}}
            job = R.Job({"experiment": "x", "task": "ag_news", "item": "1", "variant": "base", "rep": 0}, name, 1000, 10, lambda: rec)
            lab.execute([job], workers=1)
            self.assertAlmostEqual(lab.budget.spent, 1000 * 1e-6 + 10 * 5e-6)
            self.assertTrue(st.read()[0]["cost_estimated"])

    def test_plan_ne_depense_rien(self):
        with tempfile.TemporaryDirectory() as d:
            lab, st = self.lab(d)
            before = self.S.calls
            rows, total = lab.plan("smoke")
            self.assertGreater(total, 0)
            self.assertEqual(self.S.calls, before)

    def test_preregistration_complete(self):
        for k in ("delta_non_inferiorite", "ece_bon", "ece_acceptable", "gain_cout_significatif", "gain_latence_significatif",
                  "flip_max_determinisme", "tolerance_prix", "utilisable", "chute_bruit_max", "flip_permutation_max"):
            self.assertIn(k, C.PREREG)


if __name__ == "__main__":
    unittest.main()


from jev_lab import datasets as D, store as STO


def _row(task, item, ok=True, correct=True, system="jev", experiment="quality", gold="sports", pred=None, **kw):
    r = {"experiment": experiment, "task": task, "item": item, "system": system, "model": "m", "variant": "base", "rep": 0, "gold": gold,
         "primitive": "choice", "ok": ok, "status": 200 if ok else 429, "wall_s": .1, "total_s": .1, "n_attempts": 1, "attempts": [],
         "usage": {"input_tokens": 100, "output_tokens": 10, "cost": 4.2e-6}}
    if ok:
        ch = pred or (gold if correct else "world")
        r["response"] = {"answers": {"q": {"type": "choice", "choice": ch, "confidence": .9, "probabilities": {}}}}
        r["text"] = json.dumps({"choice": ch, "confidence": .9})        # lu pour les systèmes de type « chat »
    r.update(kw)
    return r


class TestCorrectionsRelecture(unittest.TestCase):
    def test_doublons_apres_reprise_ne_comptent_qu_une_fois(self):
        recs = [_row("ag_news", f"i{k}") for k in range(10)]
        recs += [_row("ag_news", "i3", ok=False), _row("ag_news", "i3", ok=True)]       # échec puis réussite du même exemple
        rows = A.tidy(recs)
        self.assertEqual(len(rows), 10)
        c = A.quality(rows)["cells"][("ag_news", "jev")]
        self.assertEqual((c["n"], c["acc"]), (10, 1.0))

    def test_le_reussi_l_emporte_meme_s_il_est_ecrit_avant_l_echec(self):
        recs = [_row("ag_news", "i1", ok=True), _row("ag_news", "i1", ok=False)]
        self.assertTrue(A.tidy(recs)[0]["ok"])

    def test_reponses_invalides_penalisees_pas_exclues(self):
        t = T.TASKS["sst5"]
        good = [{**_row("sst5", f"g{k}", gold=2, primitive="score"), "response": {"answers": {"q": {"score": 2.0, "confidence": .9, "probabilities": {"2": .9}}}}} for k in range(5)]
        bad = [{**_row("sst5", f"b{k}", gold=2, primitive="score"), "response": {"answers": {"q": {"oops": 1}}}} for k in range(5)]
        c = A.quality(A.tidy(good + bad))["cells"][("sst5", "jev")]
        self.assertAlmostEqual(c["mae"], (0 * 5 + (len(t.options) - 1) * 5) / 10)      # les invalides reçoivent l'erreur maximale
        self.assertAlmostEqual(c["valid_rate"], 0.5)

    def test_noul_invalide_vaut_un_demi_pour_l_auc(self):
        mk = lambda i, g, p: {**_row("sst2", i, gold=g, primitive="noul"), "response": {"answers": {"q": ({"noul": p} if p is not None else {})}}}
        rows = A.tidy([mk("a", True, .9), mk("b", False, .1), mk("c", True, None), mk("d", False, None)])
        c = A.quality(rows)["cells"][("sst2", "jev")]
        self.assertAlmostEqual(c["brier"], (0.01 + 0.01 + 0.25 + 0.25) / 4)

    def test_etiquette_legerement_inferieur_n_est_jamais_recommandee(self):
        # IC de l'écart entièrement négatif mais dans la marge : H1 est réfutée (borne haute < 0)
        n = 800
        jev = [_row("ag_news", f"i{k}", correct=(k % 100 != 0)) for k in range(n)]
        ref = [_row("ag_news", f"i{k}", system="ref", correct=True) for k in range(n)]
        for r in ref:
            r["usage"]["cost"] = 1e-3
        Q = A.quality(A.tidy(jev + ref))
        p = Q["pairs"][0]
        self.assertLess(p["hi"], 0)
        self.assertTrue(p["label"].startswith("légèrement inférieur") or p["label"].startswith("inférieur"), p["label"])
        vd = A.verdict(Q, {"pooled": None}, {"serial": {}}, {}, {}, {"cells": {}}, {"noise": [], "shuffle": []})
        self.assertFalse(vd["par_tache"]["ag_news"][0]["recommande"])

    def test_cout_compare_sur_les_memes_exemples(self):
        jev = [_row("ag_news", f"i{k}") for k in range(20)]
        ref = [_row("ag_news", f"i{k}", system="ref") for k in range(10)]
        for r in ref:
            r["usage"]["cost"] = 42e-6
        p = A.quality(A.tidy(jev + ref))["pairs"][0]
        self.assertAlmostEqual(p["cost_ratio"], 10.0)

    def test_macro_f1_penalise_les_fausses_alarmes_sur_classe_absente(self):
        a = M.macro_f1(["x", "x"], ["x", "x"])
        b = M.macro_f1(["x", "ghost"], ["x", "x"])
        self.assertLess(b, a)

    def test_wilson_et_bootstrap_par_grappes(self):
        lo, hi = M.wilson(1, 60)
        self.assertLess(lo, 1 / 60)
        self.assertGreater(hi, 1 / 60)
        self.assertTrue(M.bootstrap_clusters([[1, 1], [2, 2], [3, 3], [4, 4]], M.mean)[0] <= 2.5)

    def test_budget_est_cumule_entre_sessions_et_reserve_avant_appel(self):
        b = B.Budget(1.0, spent0=0.9)
        with self.assertRaises(B.BudgetExceeded):
            b.acquire(0.2)
        b.acquire(0.05)
        with self.assertRaises(B.BudgetExceeded):
            b.acquire(0.06)                      # 0,9 + 0,05 déjà réservé + 0,06 > 1
        b.release(0.05)
        b.acquire(0.06)

    def test_cle_de_reprise_inclut_le_modele(self):
        a = STO.rec_key({"experiment": "q", "task": "t", "item": "1", "system": "jev", "model": "typesafe/jev-1.13", "variant": "base", "rep": 0})
        b = STO.rec_key({"experiment": "q", "task": "t", "item": "1", "system": "jev", "model": "typesafe/jev-1.14", "variant": "base", "rep": 0})
        self.assertNotEqual(a, b)

    def test_equilibrage_reel_ou_erreur(self):
        rows_ok = [{"t": str(i), "label": str(i % 2)} for i in range(400)]
        old = D.pool
        try:
            D.pool = lambda *a, **k: rows_ok
            got = D.sample("d", "c", "s", 100, 1, label_key="label", balanced=True)
            self.assertEqual(sum(1 for r in got if r["label"] == "1"), 50)
            D.pool = lambda *a, **k: [{"t": str(i), "label": "1" if i < 5 else "0"} for i in range(400)]     # 1,25 % de positifs
            with self.assertRaises(RuntimeError):
                D.sample("d", "c", "s", 100, 1, label_key="label", balanced=True)
        finally:
            D.pool = old

    def test_lecture_robuste_des_reponses_des_references(self):
        t = T.TASKS["comptage"]
        self.assertEqual(T.parse_chat(t, '{"choice": 3, "confidence": 0.5}')["pred"], "3")             # entier au lieu de la clé "3"
        self.assertEqual(T.parse_chat(T.TASKS["ag_news"], '{"choice": " Sports ", "confidence": 0.5}')["pred"], "sports")
        self.assertEqual(T.parse_chat(T.TASKS["ag_news"], 'Exemple {oui}. Réponse : {"choice": "world", "confidence": 0.6}')["pred"], "world")
        self.assertIsNone(T.parse_chat(T.TASKS["ag_news"], '{"choice": "n_importe_quoi"}')["pred"])
        self.assertIsNone(T.parse_jev(T.TASKS["sst2"], {"noul": "abc"})["pred"])                       # pas de plantage

    def test_reponse_vide_ou_tronquee_est_un_echec_d_appel(self):
        for body_ch in ({"message": {"content": ""}, "finish_reason": "stop"}, {"message": {"content": '{"choice":'}, "finish_reason": "length"}):
            old = CL.http_json
            CL.http_json = lambda *a, **k: {"ok": True, "status": 200, "wall_s": .1, "total_s": .1, "attempts": [], "headers": {},
                                            "body": {"choices": [body_ch], "usage": {"prompt_tokens": 5, "completion_tokens": 1000}}}
            try:
                rec = CL.ChatClient("m").call({"experiment": "x", "task": "ag_news", "item": "1", "rep": 0, "variant": "base"}, "p")
            finally:
                CL.http_json = old
            self.assertFalse(rec["ok"])
            self.assertIn("vide ou tronqué", rec["error"])

    def test_meta_restaure_les_options_pour_un_rapport_relu(self):
        t = T.TASKS["banking77"]
        saved = t.options
        try:
            t.options = {}
            A.apply_meta({"task_options": {"banking77": {"a": "A", "b": "B"}}})
            self.assertEqual(set(t.options), {"a", "b"})
            self.assertIsNone(T.parse_chat(t, '{"choice": "garbage"}')["pred"])
        finally:
            t.options = saved

    def test_analyse_tolere_des_reponses_multi_questions_mal_formees(self):
        bad = {**_row("sst2", "x", primitive="noul", experiment="multi", gold={"pos": True, "neg": False}), "variant": "pair_noul",
               "response": {"answers": {"pos": {"noul": .9}}}}
        out = A.multi(A.tidy([bad]))
        self.assertEqual(out["malformed"], 1)

    def test_connexion_persistante_et_reprise_apres_fermeture(self):
        os.environ["OPENROUTER_API_KEY"] = "k"
        srv, S, url = mock.start()
        old = C.BASE
        C.set_base(url)
        try:
            body = {"model": "m", "state": {"article": "a"}, "questions": {"q": T.spec(T.TASKS["ag_news"])}}
            r1 = CL.http_json(C.JEV_URL, body)
            conn = list(CL._tls.pool.values())[0]
            r2 = CL.http_json(C.JEV_URL, body)
            self.assertTrue(r1["ok"] and r2["ok"])
            self.assertIs(list(CL._tls.pool.values())[0], conn)          # même connexion réutilisée
            conn.close()                                               # le serveur « ferme » entre deux appels
            r3 = CL.http_json(C.JEV_URL, body)
            self.assertTrue(r3["ok"])
            self.assertEqual(len(r3["attempts"]), 1)                   # reconnexion transparente, pas comptée comme échec
        finally:
            srv.shutdown()
            C.set_base(old)
