"""Tirage du quiz : simulation reproductible (Node, seed fixe) sur 2000 tirages.

Le tirage vit dans pipeline/templates/draw.js (fonctions pures, inlinées dans la page). On le teste avec tests/draw_sim.js :
  node tests/draw_sim.js [pool.json] --draws 2000 --n 15 --seed 1
Les tests sont ignorés si Node n'est pas installé.
"""
import json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from pipeline import build_site, store

NODE = shutil.which("node")
SIM = os.path.join(ROOT, "tests", "draw_sim.js")
DRAW = os.path.join(ROOT, "pipeline", "templates", "draw.js")


def sim(pool=None, *extra):
    args = [NODE, SIM]
    tmp = None
    if pool is not None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(pool, tmp); tmp.close(); args.append(tmp.name)
    try:
        out = subprocess.run(args + ["--draws", "2000", "--n", "15", "--seed", "1", *extra], capture_output=True, text=True, check=True, timeout=120)
    finally:
        if tmp:
            os.unlink(tmp.name)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "Node absent")
class DrawSynthetic(unittest.TestCase):
    """Pool volontairement déséquilibré : un thème énorme, un bloc dominant, peu de textes « supprimer »."""

    @classmethod
    def setUpClass(cls):
        cls.r = sim()
        cls.rp = sim(None, "--prio", "B,C,D")

    def test_always_n_distinct_questions(self):
        self.assertTrue(self.r["taille_ok"])

    def test_blocs_more_balanced_than_pure_random(self):
        e = self.r["ecart_bloc"]
        self.assertLess(e["equilibre"], e["temoin_hasard"] / 2, e)
        self.assertLess(e["equilibre"], e["pool"] / 2, e)       # le tirage corrige l'écart du pool lui-même

    def test_no_dominant_category(self):
        # 8 thèmes dont un représente 14/42 du pool : un tirage au hasard en met souvent 5 à 10 de ce thème
        self.assertLessEqual(self.r["equilibre"]["maxCatPerDraw"]["max"], 3)
        self.assertGreater(self.r["temoin_hasard"]["maxCatPerDraw"]["max"], 5)
        self.assertLessEqual(self.r["equilibre"]["maxCatPerDraw"]["mean"], 2.5)

    def test_polarity_mixed(self):
        e = self.r["ecart_pol"]
        self.assertLess(e["equilibre"], e["temoin_hasard"] / 2, e)

    def test_every_question_can_appear(self):
        self.assertGreaterEqual(self.r["equilibre"]["coverage"], 0.99)

    def test_priority_themes_keep_their_share(self):
        # 15 places, 60 % réservées : 9 questions des thèmes prioritaires (B, C, D en ont 12 à eux trois)
        self.assertAlmostEqual(self.rp["prio_share"], 0.6, places=2)
        self.assertTrue(self.rp["taille_ok"])


@unittest.skipUnless(NODE, "Node absent")
class DrawRealPool(unittest.TestCase):
    """Pool réel du quiz : fiches publiables de content/questions ∩ content/curated.json (si présent)."""

    def test_real_pool_balanced(self):
        cur = build_site.load_curated()
        qs = build_site.select_questions(True, True, cur)
        if len(qs) < 15:
            self.skipTest("moins de 15 fiches publiables")
        items = build_site.curated_items(cur)
        pool = [dict(n=q["n"], cat=q["cat"], bloc=(items.get(q["n"]) or {}).get("bloc") or "autre", pol=q.get("polarity") or "adopt") for q in qs]
        r = sim(pool)
        self.assertTrue(r["taille_ok"])
        self.assertLessEqual(r["ecart_bloc"]["equilibre"], r["ecart_bloc"]["temoin_hasard"], r["ecart_bloc"])
        cats = len({q["cat"] for q in pool})
        self.assertLessEqual(r["equilibre"]["maxCatPerDraw"]["max"], max(2, -(-15 // cats)) + 1)
        self.assertGreaterEqual(r["equilibre"]["coverage"], 0.99)


@unittest.skipUnless(NODE, "Node absent")
class ArgOrder(unittest.TestCase):
    def test_arg_order_is_random_then_memorised(self):
        js = ("const {argFirst}=require(%s);let s=1;const rand=()=>{s=(s*16807)%%2147483647;return s/2147483647};const memo={};"
              "const first=[];for(let n=0;n<400;n++)first.push(argFirst(memo,n,rand));"
              "const same=first.every((v,n)=>argFirst(memo,n,()=>0.99)===v);"
              "console.log(JSON.stringify({pro:first.filter(x=>x==='pro').length,con:first.filter(x=>x==='con').length,same}));") % json.dumps(DRAW)
        o = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertTrue(o["same"])                       # mémorisé pour la question
        self.assertGreater(min(o["pro"], o["con"]), 140)  # et tiré au sort (≈ 50/50 sur 400 questions)


if __name__ == "__main__":
    unittest.main()
