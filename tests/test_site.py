"""Site : pool du quiz piloté par content/curated.json (avec repli), données de la page Méthode, placeholders, schéma de jev_summary.json."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import config as C, store, build_site as B, seatmap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NODE = shutil.which("node")


def fiche(n, status, cat="Justice & sécurité", **kw):
    q = dict(n=n, status=status, cat=cat, label=f"la mesure {n}", title=f"Titre {n}", kind="texte", sum="Résumé.", pro="Pour.", con="Contre.",
             hook="Accroche.", surp="Surprise.", polarity="adopt", reviews=[], date="2026-01-10",
             sources=[{"label": "Scrutin officiel", "url": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{n}"}])
    q.update(kw)
    return q


def curated(votes, **kw):
    cur = dict(n=len(votes), n_cible=len(votes), cap_bloc=2, min_votants=150, min_div=0.2, indicateurs=["orateurs", "interventions", "duree_min", "mots"],
               entonnoir=[["Tous", 100], ["Éligibles", 30], ["Retenus", len(votes)]], limites=["Une limite."], refuses_par_plafond=[],
               repartition={"bloc": {"univers": {"gauche": 5, "droite": 5}, "eligibles": {"gauche": 3, "droite": 3}, "selection": {"gauche": 1, "droite": 2}},
                            "type": {"univers": {"proposition de loi": 8, "projet de loi": 2}, "selection": {"proposition de loi": 2, "projet de loi": 1}}},
               items=[dict(rang=i + 1, vote=v, dossier=f"D{v}", titre_dossier=f"Dossier {v}", type="proposition de loi", bloc=("gauche" if i % 2 else "droite"),
                           origine="X", vote_date="2026-01-10", vote_kind="ensemble", votants=300, signaux=dict(orateurs=10, interventions=20, duree_min=120, amendements=5, scrutins=2))
                      for i, v in enumerate(votes)])
    cur.update(kw)
    return cur


class TmpContent(unittest.TestCase):
    """Un dossier content/ temporaire : store.QDIR et config.CONTENT pointent dessus."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = (store.QDIR, C.CONTENT, C.DATA)
        store.QDIR = os.path.join(self.tmp, "questions"); C.CONTENT = self.tmp; C.DATA = os.path.join(self.tmp, "data")
        os.makedirs(store.QDIR); os.makedirs(C.DATA)

    def tearDown(self):
        store.QDIR, C.CONTENT, C.DATA = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, *fiches):
        for q in fiches:
            with open(os.path.join(store.QDIR, f"{q['n']}.json"), "w", encoding="utf-8") as f:
                json.dump(q, f)

    def put_curated(self, cur):
        with open(os.path.join(self.tmp, "curated.json"), "w", encoding="utf-8") as f:
            json.dump(cur, f)


class Selection(TmpContent):
    def setUp(self):
        super().setUp()
        self.put(fiche(1, "published"), fiche(2, "pending_review"), fiche(3, "blocked"), fiche(4, "legacy"), fiche(5, "pending_review"), fiche(6, "draft"), fiche(7, "legacy"))
        self.cur = curated([1, 2, 3, 6, 7])

    def test_only_curated_votes_and_never_blocked(self):
        got = {q["n"] for q in B.select_questions(True, True, self.cur)}
        self.assertEqual(got, {1, 2, 7})                    # 3 bloquée, 6 brouillon : jamais ; 4 et 5 hors curated.json

    def test_other_fiches_stay_in_store_but_out_of_quiz(self):
        self.assertEqual({q["n"] for q in store.all_questions()}, {1, 2, 3, 4, 5, 6, 7})
        self.assertNotIn(4, {q["n"] for q in B.select_questions(True, True, self.cur)})

    def test_options_still_apply(self):
        self.assertEqual({q["n"] for q in B.select_questions(False, True, self.cur)}, {1, 7})
        self.assertEqual({q["n"] for q in B.select_questions(True, False, self.cur)}, {1, 2})

    def test_fallback_without_curated_proposes_every_publishable_fiche(self):
        self.assertEqual({q["n"] for q in B.select_questions(True, True, None)}, {1, 2, 4, 5, 7})

    def test_load_curated_missing_or_broken_is_none(self):
        self.assertIsNone(B.load_curated())                                        # absent
        with open(os.path.join(self.tmp, "curated.json"), "w") as f:
            f.write('{"items": [{"pas_de_vote": 1}]}')
        self.assertIsNone(B.load_curated())                                        # illisible
        with open(os.path.join(self.tmp, "curated.json"), "w") as f:
            f.write("{pas du json")
        self.assertIsNone(B.load_curated())
        with open(os.path.join(self.tmp, "curated.json"), "w") as f:
            f.write("[1, 2]")
        self.assertIsNone(B.load_curated())
        self.put_curated(self.cur)
        self.assertEqual(len(B.load_curated()["items"]), 5)

    def test_make_data_carries_bloc_and_polarity_for_the_draw(self):
        sc = {str(n): dict(date="2026-01-10", sort="adopté", tot=[1, 0, 0], g={"RN": [1, 0, 0, 5]}) for n in (1, 2, 7)}
        seats = {n: ("AB",) for n in (1, 2, 7)}
        d = B.make_data(B.select_questions(True, True, self.cur), sc, seats, self.cur)
        by = {q["n"]: q for q in d["q"]}
        self.assertEqual(by[1]["bloc"], "droite"); self.assertEqual(by[2]["bloc"], "gauche"); self.assertEqual(by[1]["pol"], "adopt")
        d0 = B.make_data(B.select_questions(True, True, None), sc | {"4": sc["1"], "5": sc["1"]}, seats | {4: ("AB",), 5: ("AB",)}, None)
        self.assertTrue(all(q["bloc"] == "autre" for q in d0["q"]))                 # repli : un seul groupe, pas de faux équilibre


class MethodData(TmpContent):
    def test_blocked_stage(self):
        self.assertEqual(B.blocked_stage("sources insuffisantes pour décrire la mesure et ses critiques"), "sources")
        self.assertEqual(B.blocked_stage("sens du vote : INVERSE"), "sens")
        self.assertEqual(B.blocked_stage("orientation jugée trop forte (3.0/5, biais autre)"), "neutralite")
        self.assertEqual(B.blocked_stage("nom de parti/groupe : « RN »; résumé de 7 phrases"), "noms")
        self.assertEqual(B.blocked_stage("arguments pour/contre non pertinents ou déséquilibrés"), "pro_con")
        self.assertEqual(B.blocked_stage("catégorie invalide : 'x'"), "format")
        self.assertEqual(B.blocked_stage(None), "autre")

    def test_fiche_stats_reads_status_and_checks(self):
        ck = dict(direction=dict(ok=True), neutrality=dict(ok=True, judge=dict(score=2.0)), pro_con=dict(ok=True))
        fs = [fiche(1, "published", checks=ck), fiche(2, "pending_review", checks=ck, generator=dict(model="m1")), fiche(3, "legacy", checks={}),
              fiche(4, "blocked", blocked_reason="sources insuffisantes x"), fiche(5, "blocked", blocked_reason="sens du vote : INVERSE", checks={"direction": {"ok": False}})]
        s = B.fiche_stats(fs, 8)
        self.assertEqual((s["sujets"], s["fiches"], s["sans_fiche"], s["relues"]), (8, 5, 3, 1))
        self.assertEqual(s["par_statut"]["blocked"], 2); self.assertEqual(s["bloquees_par_etape"], {"sources": 1, "sens": 1})
        self.assertEqual(s["legacy_sans_controles"], 1); self.assertEqual(s["note_neutralite_moyenne"], 2.0); self.assertEqual(s["modeles"], ["m1"])
        self.assertEqual(s["controles"]["avec_controles"], 3); self.assertEqual(s["controles"]["sens_ok"], 2)

    def test_make_method_with_curated(self):
        allf = [fiche(1, "published"), fiche(2, "pending_review"), fiche(3, "blocked", blocked_reason="sources insuffisantes"), fiche(9, "legacy")]
        cur = curated([1, 2, 3, 4])
        pool = B.select_questions(True, True, cur) if False else [q for q in allf if q["status"] != "blocked" and q["n"] in (1, 2)]
        m = B.make_method(cur, pool, allf, None)
        self.assertTrue(m["curated"]); self.assertEqual(m["fiches"]["sujets"], 4); self.assertEqual(m["fiches"]["sans_fiche"], 1)
        self.assertEqual([i["in_quiz"] for i in m["items"]], [True, True, False, False])
        self.assertEqual([i["fiche"] for i in m["items"]], ["published", "pending_review", "blocked", None])
        self.assertIn("entonnoir", m["curated_info"]); self.assertEqual(m["pool"]["n"], 2); self.assertEqual(m["pool"]["pol"], {"adopt": 2, "remove": 0})
        self.assertIn("gauche", m["bloc_def"])
        json.dumps(m)                                                              # sérialisable tel quel

    def test_make_method_fallback_flags_it(self):
        allf = [fiche(1, "published"), fiche(2, "legacy")]
        m = B.make_method(None, allf, allf, None)
        self.assertFalse(m["curated"]); self.assertNotIn("items", m); self.assertEqual(m["fiches"]["fiches"], 2)


class JevSummary(TmpContent):
    EXAMPLE = os.path.join(ROOT, "content", "jev_summary.example.json")

    def write(self, obj, name="jev_summary.json"):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))
        return p

    def test_absent_means_study_in_progress(self):
        self.assertIsNone(B.load_jev_summary())

    def test_example_file_is_valid_and_complete(self):
        j = B.load_jev_summary(self.EXAMPLE)
        self.assertEqual(set(j), {"titre", "lede", "chiffres", "verdict", "rapport_url"})
        self.assertTrue(all({"label", "valeur"} <= set(c) for c in j["chiffres"]))
        self.assertTrue(j["rapport_url"].startswith("https://"))

    def test_real_file_when_present_is_valid(self):
        if os.path.exists(os.path.join(ROOT, "content", "jev_summary.json")):
            self.assertIsNotNone(B.load_jev_summary(os.path.join(ROOT, "content", "jev_summary.json")))

    def test_all_keys_optional(self):
        self.assertEqual(B.load_jev_summary(self.write({"lede": "Un mot."})), {"lede": "Un mot."})

    def test_invalid_content_is_ignored_not_fatal(self):
        self.assertIsNone(B.load_jev_summary(self.write("pas du json")))
        self.assertIsNone(B.load_jev_summary(self.write([1, 2])))
        self.assertIsNone(B.load_jev_summary(self.write({})))
        self.assertEqual(B.load_jev_summary(self.write({"rapport_url": "etude-jev.html"})), {"rapport_url": "etude-jev.html"})    # page du site : acceptée
        self.assertIsNone(B.load_jev_summary(self.write({"rapport_url": "../x.html"})))                                           # chemin hors site : refusé
        self.assertIsNone(B.load_jev_summary(self.write({"titre": 3, "chiffres": "x", "rapport_url": "http://non-https"})))
        j = B.load_jev_summary(self.write({"titre": "T", "chiffres": [{"label": "ok", "valeur": 12, "note": "n"}, {"label": "sans valeur"}, {"valeur": 1}, "x", {"label": "bool", "valeur": True}],
                                           "rapport_url": "javascript:alert(1)"}))
        self.assertEqual(j, {"titre": "T", "chiffres": [{"label": "ok", "valeur": 12, "note": "n"}]})   # URL non https écartée


class Template(TmpContent):
    def test_assembled_template_has_no_leftover_marker(self):
        html = B.assemble_template()
        self.assertEqual(re.findall(r"/\*__\w+__\*/", html), [])
        for p in B.PLACEHOLDERS:
            self.assertIn(p, html)

    def test_inject_fails_on_missing_or_unreplaced_placeholder(self):
        html = B.assemble_template()
        rep = {p: {} for p in B.PLACEHOLDERS}
        out = B.inject(html, rep)
        self.assertFalse(any(p in out for p in B.PLACEHOLDERS))
        with self.assertRaises(AssertionError):
            B.inject(html, {**rep, "__NOPE__": 1})
        with self.assertRaises(AssertionError):
            B.inject(html, {p: {} for p in B.PLACEHOLDERS if p != "__METHOD__"})        # un placeholder resterait

    @unittest.skipUnless(NODE, "Node absent")
    def test_page_script_is_valid_javascript(self):
        out = B.inject(B.assemble_template(), {p: {} for p in B.PLACEHOLDERS})
        js = re.search(r"<script>(.*)</script>", out, re.S).group(1)
        p = os.path.join(self.tmp, "page.js")
        open(p, "w", encoding="utf-8").write(js)
        r = subprocess.run([NODE, "--check", p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_origin_is_never_shown_during_the_quiz(self):
        src = open(C.TEMPLATE, encoding="utf-8").read()
        quiz = src[src.index("function viewQuiz"):src.index("function ranking")]
        self.assertIsNone(re.search(r"\.bloc\b|\bbloc\s*:", quiz))
        self.assertNotIn("METHOD", quiz)

    def test_method_numbers_are_injected_not_written_in_the_page(self):
        js = open(os.path.join(ROOT, "pipeline", "templates", "method.js"), encoding="utf-8").read()
        for chiffre in ("3252", "3 252", "244", "115"):
            self.assertNotIn(chiffre, js)
        self.assertIn("MC.entonnoir", js); self.assertIn("MF.relues", js)


class BuildEndToEnd(TmpContent):
    """build() complet sur des données synthétiques : avec curated.json, puis en repli."""

    def setUp(self):
        super().setUp()
        self.put(fiche(1, "pending_review"), fiche(2, "pending_review"), fiche(3, "legacy"))
        sc = {str(n): dict(date="2026-01-10", sort="adopté", titre=f"t{n}", type="SPS", dem="", tot=[250, 100, 10], g={"RN": [10, 0, 0, 20, 0], "SOC": [0, 10, 0, 20, 0]}) for n in (1, 2, 3)}
        C.jdump(sc, os.path.join(C.DATA, "scrutins.json"))
        self._seat = seatmap.build
        seatmap.build = lambda dates, **k: {n: ("AB" * 10, 0) for n in dates}
        self.out = os.path.join(self.tmp, "site")

    def tearDown(self):
        seatmap.build = self._seat
        super().tearDown()

    def method_of(self):
        html = open(os.path.join(self.out, "index.html"), encoding="utf-8").read()
        self.assertFalse(any(p in html for p in B.PLACEHOLDERS))
        return json.loads(re.search(r"const METHOD = (\{.*?\});\nconst POOL", html, re.S).group(1))

    def test_build_with_curated_restricts_pool(self):
        self.put_curated(curated([2, 3]))
        d = B.build(self.out)
        self.assertEqual({q["n"] for q in d["q"]}, {2, 3})                         # la fiche 1 reste en base mais hors quiz
        m = self.method_of()
        self.assertTrue(m["curated"]); self.assertEqual(m["pool"]["n"], 2); self.assertEqual(len(m["items"]), 2)
        self.assertEqual(m["curated_info"]["entonnoir"][0][1], 100)                # chiffre lu de curated.json
        self.assertTrue(json.load(open(os.path.join(self.out, "status.json")))["curated"])
        self.assertEqual(json.load(open(os.path.join(self.out, "data.json")))["selection"], "curated.json")

    def test_build_without_curated_falls_back_explicitly(self):
        d = B.build(self.out)
        self.assertEqual({q["n"] for q in d["q"]}, {1, 2, 3})
        m = self.method_of()
        self.assertFalse(m["curated"]); self.assertNotIn("items", m)
        self.assertFalse(json.load(open(os.path.join(self.out, "status.json")))["curated"])
        self.assertIn("repli", json.load(open(os.path.join(self.out, "data.json")))["selection"])

    def test_jev_summary_reaches_the_page_when_present(self):
        self.put_curated(curated([2, 3]))
        with open(os.path.join(self.tmp, "jev_summary.json"), "w", encoding="utf-8") as f:
            json.dump({"titre": "Étude", "rapport_url": "https://exemple.org/rapport"}, f)
        B.build(self.out)
        self.assertEqual(self.method_of()["jev"], {"titre": "Étude", "rapport_url": "https://exemple.org/rapport"})

    def test_jev_summary_absent_gives_null(self):
        self.put_curated(curated([2, 3]))
        B.build(self.out)
        self.assertIsNone(self.method_of()["jev"])

    def test_empty_pool_stops_the_build(self):
        self.put_curated(curated([99]))
        with self.assertRaises(SystemExit):
            B.build(self.out)


if __name__ == "__main__":
    unittest.main()
