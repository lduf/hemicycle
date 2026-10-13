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
