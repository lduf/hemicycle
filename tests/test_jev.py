import io, json, os, sys, unittest, urllib.error
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import classify, config as C, fiche, jev, neutrality as N
from tests.test_pipeline import GOOD  # noqa: E402


def http_error(code, body="", headers=None):
    return urllib.error.HTTPError("u", code, "x", headers or {}, io.BytesIO(body.encode()))


class WithKey(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"; os.environ["HEMI_CLASSIFIER"] = "auto"; os.environ["HEMI_LLM"] = "none"
        os.environ.pop("HEMI_ALLOW_NO_JUDGE", None)
        jev.STATS.update(calls=0, input_tokens=0, cost=0.0)

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._env)


class Client(WithKey):
    def test_unavailable_without_key(self):
        os.environ.pop("OPENROUTER_API_KEY")
        self.assertFalse(jev.available())
        with self.assertRaises(jev.JevError):
            jev.decide("x", {"q": jev.noul("?")})

    def test_builders_validate_bounds(self):
        with self.assertRaises(ValueError): jev.score("?", ["un seul"])
        with self.assertRaises(ValueError): jev.choice("?", {"a": "x"})
        self.assertEqual(jev.noul("?")["type"], "noul")

    def test_decide_parses_and_accumulates_usage(self):
        resp = {"answers": {"q": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": 100, "cost": 0.001}, "model": "typesafe/jev-1.13-x"}
        with mock.patch.object(jev, "_post", return_value=resp) as p:
            r = jev.decide({"a": 1}, {"q": jev.noul("?")})
        self.assertEqual(r["answers"]["q"]["noul"], 0.9)
        self.assertEqual(p.call_args[0][0]["model"], jev.MODEL)
        self.assertEqual((jev.STATS["calls"], jev.STATS["input_tokens"]), (1, 100))

    def test_retries_transient_then_succeeds_but_not_client_errors(self):
        ok = {"answers": {"q": {"type": "noul", "noul": 0.1}}}
        with mock.patch("time.sleep"), mock.patch.object(jev, "_post", side_effect=[http_error(429), http_error(503), ok]) as p:
            jev.decide("s", {"q": jev.noul("?")})
        self.assertEqual(p.call_count, 3)
        with mock.patch("time.sleep"), mock.patch.object(jev, "_post", side_effect=[http_error(400, "bad")]) as p:
            with self.assertRaises(jev.JevError):
                jev.decide("s", {"q": jev.noul("?")})
        self.assertEqual(p.call_count, 1)
        with mock.patch("time.sleep"), mock.patch.object(jev, "_post", side_effect=[http_error(402, "openrouter_in_flight_budget"), ok]) as p:
            jev.decide("s", {"q": jev.noul("?")})
        with mock.patch("time.sleep"), mock.patch.object(jev, "_post", side_effect=[http_error(402, "insufficient credits")]):
            with self.assertRaises(jev.JevError):   # crédits épuisés : pas de réessai, échec fermé
                jev.decide("s", {"q": jev.noul("?")})

    def test_missing_answer_is_an_error(self):
        with mock.patch.object(jev, "_post", return_value={"answers": {}}):
            with self.assertRaises(jev.JevError):
                jev.decide("s", {"q": jev.noul("?")})


def fake(answers):
    def _d(state, questions, engine=None):
        return {"answers": {k: answers[k] for k in questions}, "usage": {}, "model": "m"}
    return _d


class Tasks(WithKey):
    def test_backend_selection(self):
        self.assertEqual(classify.backend(), "jev")
        os.environ["HEMI_CLASSIFIER"] = "none"; self.assertIsNone(classify.backend())
        os.environ["HEMI_CLASSIFIER"] = "claude"; self.assertIsNone(classify.backend())   # HEMI_LLM=none
        os.environ.pop("OPENROUTER_API_KEY"); os.environ["HEMI_CLASSIFIER"] = "auto"; self.assertIsNone(classify.backend())

    def test_category(self):
        a = {"cat": {"type": "choice", "choice": "Logement", "confidence": 0.9, "probabilities": {"Logement": .9}}}
        with mock.patch.object(jev, "decide", fake(a)):
            r = classify.category(dict(title="t", label="l", sum="s"))
        self.assertEqual((r["cat"], r["engine"]), ("Logement", "jev"))
        self.assertTrue(set(classify.CAT_DESC) == set(C.CATS))   # toutes les catégories sont décrites, aucune en trop

    def test_direction_requires_matching_sense_and_confidence(self):
        good = {"correspond": {"noul": .95}, "sens": {"choice": "supprimer"}}
        with mock.patch.object(jev, "decide", fake(good)):
            self.assertTrue(classify.direction("titre", "la taxe X", "remove")[0])
            self.assertFalse(classify.direction("titre", "la taxe X", "adopt")[0])      # sens attendu = adopter
        weak = {"correspond": {"noul": .6}, "sens": {"choice": "adopter"}}
        with mock.patch.object(jev, "decide", fake(weak)):
            self.assertFalse(classify.direction("titre", "la taxe X", "adopt")[0])
        doubt = {"correspond": {"noul": .99}, "sens": {"choice": "douteux"}}
        with mock.patch.object(jev, "decide", fake(doubt)):
            self.assertFalse(classify.direction("titre", "x", "adopt")[0])

    def test_pro_con_thresholds(self):
        base = {"pro_ok": {"noul": .95}, "con_ok": {"noul": .95}, "pro_fond": {"noul": .9}, "con_fond": {"noul": .9}, "equilibre": {"score": 1.0}}
        with mock.patch.object(jev, "decide", fake(base)):
            self.assertTrue(classify.pro_con(GOOD)["ok"])
        for k, v in (("con_ok", {"noul": .2}), ("pro_fond", {"noul": .1}), ("equilibre", {"score": 1.9})):
            with mock.patch.object(jev, "decide", fake(dict(base, **{k: v}))):
                self.assertFalse(classify.pro_con(GOOD)["ok"], k)

    def test_sources_sufficient(self):
        with mock.patch.object(jev, "decide", fake({"decrit": {"noul": .9}, "critiques": {"noul": .1}})):
            self.assertFalse(classify.sources_sufficient("t", ["x"])[0])
        with mock.patch.object(jev, "decide", fake({"decrit": {"noul": .9}, "critiques": {"noul": .8}})):
            self.assertTrue(classify.sources_sufficient("t", ["x"])[0])

    def test_orientation_feeds_neutrality_gate(self):
        def ans(score):
            return {"orientation": {"score": score}, "bord": {"choice": "aucun", "probabilities": {}}, "charge": {"noul": .1}}
        with mock.patch.object(jev, "decide", fake(ans(1.0))):
            self.assertTrue(N.evaluate(GOOD, actors={})["ok"])
        with mock.patch.object(jev, "decide", fake(ans(3.4))):
            ev = N.evaluate(GOOD, actors={})
            self.assertFalse(ev["ok"]); self.assertEqual(ev["judge"]["engine"], "jev")

    def test_neutrality_jev_outage_fails_closed(self):
        with mock.patch.object(jev, "decide", side_effect=jev.JevError("down")):
            self.assertFalse(N.evaluate(GOOD, actors={})["ok"])


class Pipeline(WithKey):
    def test_full_check_with_jev_overrides_nothing_when_all_ok(self):
        answers = {"correspond": {"noul": .97}, "sens": {"choice": "adopter"},
                   "orientation": {"score": 1.0}, "bord": {"choice": "aucun", "probabilities": {}}, "charge": {"noul": .05},
                   "pro_ok": {"noul": .9}, "con_ok": {"noul": .9}, "pro_fond": {"noul": .9}, "con_fond": {"noul": .9}, "equilibre": {"score": 1.0}}
        q = json.loads(json.dumps(dict(GOOD, cat="Famille & social", status="draft")))
        with mock.patch.object(jev, "decide", fake(answers)):
            out = fiche.check(q)
        self.assertEqual(out["status"], "pending_review", out.get("blocked_reason"))
        self.assertIsNotNone(out["checks"]["pro_con"])

    def test_pro_con_failure_blocks(self):
        answers = {"correspond": {"noul": .97}, "sens": {"choice": "adopter"},
                   "orientation": {"score": 1.0}, "bord": {"choice": "aucun", "probabilities": {}}, "charge": {"noul": .05},
                   "pro_ok": {"noul": .9}, "con_ok": {"noul": .1}, "pro_fond": {"noul": .9}, "con_fond": {"noul": .9}, "equilibre": {"score": 1.0}}
        q = json.loads(json.dumps(dict(GOOD, cat="Famille & social", status="draft")))
        with mock.patch.object(jev, "decide", fake(answers)):
            out = fiche.check(q)
        self.assertEqual(out["status"], "blocked"); self.assertIn("pertinents", out["blocked_reason"])

    def test_category_overrides_writer_when_confident(self):
        r = dict(title="t", label="l", cat="Sport", hook="h", sum=GOOD["sum"], pro=GOOD["pro"], con=GOOD["con"], surp="", source_ids=[1])
        answers = {"cat": {"choice": "Logement", "confidence": .9}}
        s = dict(n=9, date="2026-01-01", titre="l'ensemble du projet de loi X", sort="adopté")
        # on isole la catégorie : check() est neutralisé
        with mock.patch.object(jev, "decide", fake(answers)), mock.patch.object(fiche, "check", side_effect=lambda q, call_judge=None: q):
            q = fiche.draft(s, [], call=lambda p: r, texts=[("https://www.senat.fr/x", "texte")])
        self.assertEqual((q["cat"], q["cat_check"]["writer"]), ("Logement", "Sport"))


if __name__ == "__main__":
    unittest.main()


class Bench(unittest.TestCase):
    def test_auc_and_youden(self):
        from pipeline import bench_jev as B
        self.assertEqual(B.auc([3, 4], [1, 2]), 1.0)
        self.assertEqual(B.auc([1, 2], [3, 4]), 0.0)
        self.assertEqual(B.auc([2], [2]), 0.5)
        self.assertEqual(B.youden([3, 4, 5], [1, 2, 3])[0], 3)
