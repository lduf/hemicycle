import gzip, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import config as C, direction as D, select_votes as SV, neutrality as N, review, store, ingest, seatmap, promises, fiche


class Direction(unittest.TestCase):
    def test_whole_text(self):
        c = D.classify("l'ensemble de la proposition de loi visant à rendre accessible le repas à 1 €")
        self.assertEqual((c["kind"], c["polarity"]), ("ensemble", "adopt"))

    def test_suppression_inverts(self):
        c = D.classify("l'amendement de suppression n° 828 de M. X et l'amendement identique suivant à l'article 6 du projet de loi")
        self.assertEqual(c["polarity"], "remove")

    def test_restore(self):
        self.assertEqual(D.classify("l'amendement de rétablissement n° 12 de l'article 3")["polarity"], "adopt")

    def test_conflicting_is_doubtful(self):
        self.assertIsNone(D.classify("l'amendement de suppression ... et de rétablissement ...")["polarity"])

    def test_procedure_and_subamendment_blocked(self):
        self.assertIsNone(D.classify("la motion de renvoi en commission")["polarity"])
        self.assertIsNone(D.classify("le sous-amendement n° 5 à l'amendement n° 4")["polarity"])

    def test_unknown_blocked(self):
        self.assertIsNone(D.classify("quelque chose d'inattendu")["polarity"])

    def test_labels(self):
        self.assertEqual(D.button_labels("l'interdiction des PFAS", "adopt"), ("Pour l'interdiction des PFAS", "Contre l'interdiction des PFAS"))
        self.assertEqual(D.button_labels("l'interdiction des PFAS", "remove")[0], "Pour la suppression de l'interdiction des PFAS")
        self.assertEqual(D.button_labels("le gel des retraites", "remove")[0], "Pour la suppression du gel des retraites")

    def test_llm_check_prompt_uses_real_button_label(self):
        seen = []
        D.llm_check(lambda p: seen.append(p) or "OK", "t", "la taxe X", "remove")
        self.assertIn("Pour la suppression de la taxe X", seen[0])

    def test_llm_check_fails_closed(self):
        self.assertFalse(D.llm_check(lambda p: "DOUTE", "t", "x", "adopt")[0])
        self.assertFalse(D.llm_check(lambda p: None, "t", "x", "adopt")[0])
        self.assertTrue(D.llm_check(lambda p: "OK", "t", "x", "adopt")[0])


def scr(n, g, titre="l'ensemble du projet de loi X", typ="SPS", sort="adopté"):
    gg = {k: list(v) + [100, 0] for k, v in g.items()}
    tot = [sum(v[0] for v in g.values()), sum(v[1] for v in g.values()), sum(v[2] for v in g.values())]
    return dict(n=n, date="2026-01-01", titre=titre, type=typ, sort=sort, dem="", tot=tot, g=gg)


GROUPS = ["RN", "EPR", "LFI-NFP", "SOC", "DR", "ECOS", "DEM", "HOR", "LIOT", "GDR", "UDR"]


class Select(unittest.TestCase):
    def test_divergent_beats_consensus(self):
        split = scr(1, {g: ((60, 0, 0) if i % 2 else (0, 60, 0)) for i, g in enumerate(GROUPS)})
        same = scr(2, {g: (60, 0, 0) for g in GROUPS})
        c = SV.candidates({"1": split, "2": same})
        self.assertEqual([x["n"] for x in c], [1])

    def test_low_participation_and_taken_excluded(self):
        small = scr(3, {g: ((5, 0, 0) if i % 2 else (0, 5, 0)) for i, g in enumerate(GROUPS)})
        self.assertEqual(SV.candidates({"3": small}), [])
        split = scr(4, {g: ((60, 0, 0) if i % 2 else (0, 60, 0)) for i, g in enumerate(GROUPS)})
        self.assertEqual(SV.candidates({"4": split}, taken={4}), [])

    def test_one_reading_per_law(self):
        g = {g: ((60, 0, 0) if i % 2 else (0, 60, 0)) for i, g in enumerate(GROUPS)}
        a = scr(6, g, titre="l'ensemble du projet de loi X (première lecture)"); b = scr(7, g, titre="l'ensemble du projet de loi X (nouvelle lecture)")
        self.assertEqual(len(SV.candidates({"6": a, "7": b})), 1)
        self.assertEqual(SV.candidates({"6": a, "7": b}, taken={6}), [])

    def test_procedure_excluded(self):
        p = scr(5, {g: ((60, 0, 0) if i % 2 else (0, 60, 0)) for i, g in enumerate(GROUPS)}, titre="la motion de renvoi en commission")
        self.assertEqual(SV.candidates({"5": p}), [])


GOOD = dict(n=1, title="Interdire les écrans en crèche", label="l'interdiction des écrans en crèche", hook="Si tu as un petit frère.",
            sum="La loi interdit les écrans. Elle vise les enfants de moins de trois ans. Elle prévoit des sanctions légères. Elle laisse une exception pédagogique.",
            pro="Protéger le développement des tout-petits est une priorité de santé publique.",
            con="Certains jugent la mesure difficile à contrôler et attentatoire à la liberté des familles.",
            surp="", sources=[dict(label="s", url="https://www.assemblee-nationale.fr/dyn/17/scrutins/1")], polarity="adopt", status="pending_review", reviews=[])


class Neutrality(unittest.TestCase):
    def test_good_passes(self):
        self.assertEqual(N.deterministic(GOOD, actors={}), [])

    def test_party_name_blocked(self):
        q = dict(GOOD, sum=GOOD["sum"] + " Le Rassemblement National a voté pour.")
        self.assertTrue(any("parti" in i for i in N.deterministic(q, actors={})))

    def test_person_name_blocked(self):
        q = dict(GOOD, con=GOOD["con"] + " M. Dupont s'y oppose.")
        self.assertTrue(any("personne" in i for i in N.deterministic(q, actors={})))
        q = dict(GOOD, con=GOOD["con"] + " Jean Martin s'y oppose.")
        self.assertTrue(any("Jean Martin" in i for i in N.deterministic(q, actors={"x": ["Martin", "Jean"]})))

    def test_loaded_word_and_asymmetry_and_length(self):
        self.assertTrue(any("orienté" in i for i in N.deterministic(dict(GOOD, hook="Une loi scandaleuse."), actors={})))
        self.assertTrue(any("asymétrie" in i for i in N.deterministic(dict(GOOD, pro="Oui."), actors={})))
        self.assertTrue(any("résumé" in i for i in N.deterministic(dict(GOOD, sum="Une seule phrase."), actors={})))

    def test_fail_closed_without_judge(self):
        os.environ.pop("HEMI_ALLOW_NO_JUDGE", None); os.environ["HEMI_LLM"] = "none"
        ev = N.evaluate(GOOD, actors={})
        self.assertFalse(ev["ok"])

    def test_judge_threshold(self):
        ev = N.evaluate(GOOD, call=lambda p: {"score": 4, "biais": "droite", "raisons": []}, actors={})
        self.assertFalse(ev["ok"])
        ev = N.evaluate(GOOD, call=lambda p: {"score": 1, "biais": "aucun", "raisons": []}, actors={})
        self.assertTrue(ev["ok"])


class WithTmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = (C.CONTENT, C.DATA, store.QDIR)
        C.CONTENT = self.tmp.name; C.DATA = self.tmp.name; store.QDIR = os.path.join(self.tmp.name, "questions")

    def tearDown(self):
        C.CONTENT, C.DATA, store.QDIR = self._old
        self.tmp.cleanup()


class Review(WithTmp):
    def test_needs_both_sides_and_two_people(self):
        store.save(json.loads(json.dumps(GOOD)))
        review.sign(1, "Ana", "gauche", "approve")
        self.assertEqual(store.load(1)["status"], "pending_review")
        review.sign(1, "Ben", "gauche", "approve")           # 2 personnes mais même bord
        self.assertEqual(store.load(1)["status"], "pending_review")
        review.sign(1, "Cléo", "droite", "approve")
        self.assertEqual(store.load(1)["status"], "published")

    def test_same_person_twice_does_not_count(self):
        store.save(json.loads(json.dumps(GOOD)))
        review.sign(1, "Ana", "gauche", "approve"); review.sign(1, "ana", "droite", "approve")
        self.assertEqual(store.load(1)["status"], "pending_review")

    def test_edit_invalidates_reviews(self):
        store.save(json.loads(json.dumps(GOOD)))
        review.sign(1, "Ana", "gauche", "approve"); review.sign(1, "Ben", "droite", "approve")
        q = store.load(1); self.assertEqual(q["status"], "published")
        q["pro"] += " Ajout."
        self.assertFalse(review.can_publish(q)[0])

    def test_reject(self):
        store.save(json.loads(json.dumps(GOOD)))
        review.sign(1, "Ana", "droite", "reject", "orienté")
        self.assertEqual(store.load(1)["status"], "rejected")
        self.assertIn(1, C.jload(os.path.join(C.CONTENT, "rejected.json")))


class Ingest(unittest.TestCase):
    def test_parse_scrutin_merges_alias_and_skips_moc(self):
        s = {"numero": "9", "dateScrutin": "2026-01-02", "titre": "l’ensemble de X", "typeVote": {"codeTypeVote": "SPS"}, "sort": {"code": "adopté"},
             "demandeur": {"texte": "Gouvernement"}, "syntheseVote": {"decompte": {"pour": "2", "contre": "1", "abstentions": "0"}},
             "ventilationVotes": {"organe": {"groupes": {"groupe": [
                 {"organeRef": "PO847173", "nombreMembresGroupe": "10", "vote": {"decompteVoix": {"pour": "2", "contre": "0", "abstentions": "0"},
                  "decompteNominatif": {"pours": {"votant": {"acteurRef": "PA1", "parDelegation": "true", "numPlace": "12"}}, "contres": None}}},
                 {"organeRef": "PO872880", "nombreMembresGroupe": "5", "vote": {"decompteVoix": {"pour": "0", "contre": "1", "abstentions": "0"},
                  "decompteNominatif": {"contres": {"votant": [{"acteurRef": "PA2", "parDelegation": "false", "numPlace": "13"}]}}}}]}}}}
        f, v = ingest.parse_scrutin(s, {})
        self.assertEqual(f["g"]["UDR"], [2, 1, 0, 15, 1])
        self.assertEqual(f["titre"], "l'ensemble de X")
        self.assertEqual(sorted(v), [["PA1", 12, "UDR", "p"], ["PA2", 13, "UDR", "c"]])
        s["typeVote"]["codeTypeVote"] = "MOC"
        self.assertIsNone(ingest.parse_scrutin(s, {}))


class Seats(unittest.TestCase):
    def test_absent_placed_at_last_known_seat_and_sorted_left_to_right(self):
        p = os.path.join(tempfile.mkdtemp(), "v.jsonl.gz")
        with gzip.open(p, "wt") as f:
            f.write(json.dumps({"n": 1, "d": "2026-01-10", "v": [["A", 100, "GDR", "p"], ["B", 5, "RN", "c"]]}) + "\n")
            f.write(json.dumps({"n": 2, "d": "2026-01-12", "v": [["A", 100, "GDR", "p"], ["B", 5, "RN", "p"], ["C", 50, "SOC", "p"]]}) + "\n")
        r = seatmap.build({1: "2026-01-10"}, voters_path=p, min_seats=1)
        s = r[1][0]
        self.assertEqual(s, "ApCxBc"[0:2] + "D" + "x" + "K" + "c" if False else s)  # structure vérifiée ci-dessous
        self.assertEqual([s[i:i + 2] for i in range(0, len(s), 2)], ["Ap", "Dx", "Kc"])  # place 100 (gauche) -> 50 -> 5 (droite) ; C absent


class Promises(unittest.TestCase):
    def test_matching_proposes_only_related_and_not_displayed(self):
        progs = [dict(id="t", bloc="X", groups=["RN"], promesses=[dict(id="t1", text="Relancer la construction de réacteurs nucléaires", theme="énergie"),
                                                                    dict(id="t2", text="Interdire les téléphones portables au lycée")])]
        qs = [dict(n=1, title="Relance du nucléaire", label="la relance du nucléaire", sum="Construction de réacteurs", status="legacy")]
        d = tempfile.mkdtemp(); old = promises.MATCHES; promises.MATCHES = os.path.join(d, "m.json")
        try:
            self.assertEqual(promises.propose(questions=qs, progs=progs), 1)
            m = C.jload(promises.MATCHES)
            self.assertEqual(m["1"][0]["status"], "proposed")
            self.assertEqual(promises.usable(m)["1"], [])
            promises.confirm(1, 0, "pour")
            self.assertEqual(len(promises.usable(C.jload(promises.MATCHES))["1"]), 1)
        finally:
            promises.MATCHES = old

    def test_coverage_flags_missing_groups(self):
        cov = promises.coverage([dict(groups=["RN"], promesses=[1, 2])])
        self.assertEqual(cov["RN"], 2); self.assertEqual(cov["DR"], 0)


class Fiche(WithTmp):
    def test_blocked_when_no_llm(self):
        os.environ["HEMI_LLM"] = "none"
        s = dict(n=9, date="2026-01-01", titre="l'ensemble du projet de loi X", sort="adopté")
        q = fiche.draft(s, [], texts=[("https://www.senat.fr/x", "texte")])
        self.assertEqual(q["status"], "blocked")

    def test_doubtful_direction_blocked_before_any_call(self):
        called = []
        s = dict(n=9, date="2026-01-01", titre="le sous-amendement n° 4", sort="rejeté")
        q = fiche.draft(s, [], call=lambda p: called.append(p), texts=[("https://www.senat.fr/x", "t")])
        self.assertEqual(q["status"], "blocked"); self.assertEqual(called, [])

    def test_good_generation_reaches_review(self):
        os.environ["HEMI_ALLOW_NO_JUDGE"] = "1"
        try:
            s = dict(n=9, date="2026-01-01", titre="l'ensemble du projet de loi X", sort="adopté")
            r = dict(title=GOOD["title"], label=GOOD["label"], cat="Famille & social", hook=GOOD["hook"], sum=GOOD["sum"], pro=GOOD["pro"],
                     con=GOOD["con"], surp="", source_ids=[1])
            q = fiche.draft(s, [], call=lambda p: r, texts=[("https://www.senat.fr/x", "texte")])
            self.assertEqual(q["status"], "pending_review", q.get("blocked_reason"))
            self.assertEqual(q["sources"][0]["url"], "https://www.assemblee-nationale.fr/dyn/17/scrutins/9")
        finally:
            os.environ.pop("HEMI_ALLOW_NO_JUDGE")

    def test_domain_allowlist(self):
        from pipeline import sources
        self.assertTrue(sources.allowed("https://www.assemblee-nationale.fr/x"))
        self.assertFalse(sources.allowed("https://evil.example.com/assemblee-nationale.fr"))
        self.assertFalse(sources.allowed("http://www.senat.fr/x"))


if __name__ == "__main__":
    unittest.main()
