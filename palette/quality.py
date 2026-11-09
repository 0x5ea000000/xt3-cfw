"""Plain-language reading of a fit report. Thresholds come from two looks so far (Frontier 3.76, Noritsu 2.52) and earlier fits,
so they are guidance, not a proof: only photos from the camera settle a look."""


def verdict(rep):
    h = rep['held_out_mean']; t = h['table']['mean']; before = h['before']['mean']; s = rep['sanity']
    if t <= 3.0:
        grade, text = 'great', 'Very close to Lightroom on photos the fit never saw.'
    elif t <= 4.5:
        grade, text = 'good', 'Close to Lightroom on photos the fit never saw.'
    elif t <= 6.5:
        grade, text = 'fair', 'Recognisable, with visible differences. Check the comparisons before using it.'
    else:
        grade, text = 'poor', 'A colour table cannot reproduce this look well. It may rely on effects a table cannot do.'
    notes = []
    if not s.get('grey_L_monotone', True):
        notes.append(dict(level='warn', text='Greys do not get steadily brighter through the table. Look for banding or odd tones in smooth areas.'))
    if h['table']['p95'] > 9:
        notes.append(dict(level='warn', text=f"The worst 5% of pixels miss by {h['table']['p95']:.1f} or more. Check the highlights and strong colours."))
    if s.get('grey_max_chroma', 0) > 8:
        notes.append(dict(level='info', text='This look tints neutral greys. Check the comparisons to confirm the tint is in Lightroom too.'))
    gain = before - t
    if gain < 2:
        notes.append(dict(level='info', text='The look is close to plain PRO Neg. Std, so the table has little to do.'))
    per = sorted(((n, v['table']['mean']) for n, v in rep['held_out'].items()), key=lambda x: -x[1])
    med = per[len(per) // 2][1]
    bad = [n for n, v in per if v > 2 * med and v > 4]
    if bad:
        notes.append(dict(level='info', text=f"{len(bad)} photo{'s miss' if len(bad) != 1 else ' misses'} much more than the rest. Lightroom may be adapting to those scenes."))
    return dict(grade=grade, text=text, score=t, before=before, median=h['table']['median'], p95=h['table']['p95'], notes=notes, worst=[n for n, _ in per[:3]])
