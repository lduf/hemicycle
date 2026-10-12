"""Étape 8 : carte « Le vote de la semaine » (PNG 1080×1350) pour les réseaux. Aucun nom de parti ni de personne :
on montre l'hémicycle réel (couleur = vote) et on invite à jouer. Choisit, parmi les fiches affichables des 7 derniers
jours, le scrutin le plus clivant (divergence entre groupes) ; sinon le plus récent."""
import datetime as dt, math, os, textwrap
from . import config as C, seatmap, select_votes as SV, build_site as B

W, H = 1080, 1350
COL = {"p": (46, 160, 120), "c": (214, 80, 70), "a": (240, 180, 50), "x": (200, 205, 215)}


def pick(questions, scrutins, today):
    lo = (today - dt.timedelta(days=7)).isoformat()
    cand = [q for q in questions if lo <= scrutins[str(q["n"])]["date"] <= today.isoformat()]
    if not cand:
        return None
    def key(q):
        f = SV.features(scrutins[str(q["n"])])
        return (f["div"] if f else 0, scrutins[str(q["n"])]["date"])
    return max(cand, key=key)


def seat_xy(i, total, cx=W / 2, cy=915, r0=190, r1=400):
    """Répartition en arcs concentriques de gauche à droite (disposition schématique, l'ordre est réel)."""
    rows = 8
    radii = [r0 + (r1 - r0) * k / (rows - 1) for k in range(rows)]
    arcs = [math.pi * r for r in radii]
    tot_arc = sum(arcs)
    per = [round(total * a / tot_arc) for a in arcs]
    per[-1] += total - sum(per)
    pts = []
    for r, k in zip(radii, per):
        for j in range(k):
            ang = math.pi - math.pi * (j + .5) / k
            pts.append((ang, r))
    pts.sort(key=lambda t: -t[0])   # gauche (angle π) -> droite (0)
    ang, r = pts[i]
    return cx + r * math.cos(ang), cy - r * math.sin(ang)


def render(q, scrutin, seats_str, path):
    from PIL import Image, ImageDraw, ImageFont
    def font(sz, bold=False):
        for f in ("/usr/share/fonts/opentype/inter/Inter-Bold.otf" if bold else "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.exists(f):
                return ImageFont.truetype(f, sz)
        return ImageFont.load_default()
    im = Image.new("RGB", (W, H), (18, 24, 44)); d = ImageDraw.Draw(im)
    d.text((60, 70), "LE VOTE DE LA SEMAINE", font=font(34, True), fill=(130, 190, 255))
    y = 140
    for line in textwrap.wrap(textwrap.shorten(q["title"], 78, placeholder="…"), 26)[:3]:
        d.text((60, y), line, font=font(64, True), fill=(255, 255, 255)); y += 78
    if q.get("hook"):
        y += 10
        for line in textwrap.wrap(textwrap.shorten(q["hook"], 86, placeholder="…"), 44)[:2]:
            d.text((60, y), line, font=font(34), fill=(205, 215, 235)); y += 44
    n = len(seats_str) // 2
    for i in range(n):
        x, yy = seat_xy(i, n)
        d.ellipse((x - 9, yy - 9, x + 9, yy + 9), fill=COL[seats_str[2 * i + 1]])
    p, c, a = scrutin["tot"]
    d.text((W / 2, 960), f"{p} pour · {c} contre · {a} abstentions", font=font(40, True), fill=(255, 255, 255), anchor="mm")
    d.text((W / 2, 1015), f"Le {scrutin['date'][8:]}/{scrutin['date'][5:7]}/{scrutin['date'][:4]} — {'adopté' if scrutin['sort'] == 'adopté' else 'rejeté'}",
           font=font(30), fill=(205, 215, 235), anchor="mm")
    x0 = 330
    for lab, k in (("pour", "p"), ("contre", "c"), ("abstention", "a"), ("absent", "x")):
        d.ellipse((x0, 1075, x0 + 18, 1093), fill=COL[k]); d.text((x0 + 26, 1068), lab, font=font(24), fill=(205, 215, 235)); x0 += 120 if k != "a" else 170
    d.rounded_rectangle((60, 1150, W - 60, 1270), 40, fill=(70, 130, 255))
    d.text((W / 2, 1210), "Et toi, tu aurais voté quoi ?", font=font(46, True), fill=(255, 255, 255), anchor="mm")
    d.text((W / 2, 1310), "Données : Assemblée nationale · Licence Ouverte · votes réels, pas des promesses", font=font(22), fill=(150, 165, 195), anchor="mm")
    os.makedirs(os.path.dirname(path), exist_ok=True); im.save(path, optimize=True)


def run(out_dir=None, today=None):
    today = today or dt.date.today(); out_dir = out_dir or C.SITE
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    qs = B.select_questions()
    q = pick(qs, sc, today)
    if not q:
        print("[card] aucun vote affichable cette semaine : pas de carte"); return None
    seats = seatmap.build({q["n"]: sc[str(q["n"])]["date"]})[q["n"]][0]
    path = os.path.join(out_dir, "carte-semaine.png"); render(q, sc[str(q["n"])], seats, path)
    C.jdump(dict(n=q["n"], title=q["title"], date=sc[str(q["n"])]["date"]), os.path.join(out_dir, "carte-semaine.json"))
    print(f"[card] {q['n']} -> {path}"); return path


if __name__ == "__main__":
    run()
