"""Which listening lane a Pitchfork genre set belongs to.

Two places classify a review's genres: the catalogue harvest, which stamps
`cluster_hint` on every candidate, and the Critics Desk selector. They each
carried their own copy of the rules and disagreed in two ways, both of which
shipped visibly on the site in issue 004:

  * **"experimental" outranked "rock" in both.** A rock record carrying
    Pitchfork's secondary "experimental" tag was filed under Beats & IDM.
    The Meadowlands ("experimental,rock") was the album of the week under an
    IDM lane tag, and Psychocandy ("rock,experimental") sat beside it. In
    Pitchfork's taxonomy "experimental" is a modifier that co-occurs with a
    real genre, never a primary one, so it classifies only when nothing else
    does. It sorts last.

  * **They disagreed about rock.** The harvest sent every rock record to the
    punk turn; the selector split them by review era. The harvest's hint wins
    for the album of the week, so the cruder answer was the one that shipped.

Both rules live here now, so the two callers cannot drift apart again.
"""

# Most specific genre first; "experimental" last, for the reason above.
#
# "global" sits above "electronic" deliberately. The two source lists
# disagreed here as well (the harvest ranked global first, the desk ranked
# electronic first), so unifying them forced a choice. Global is the rarer and
# more informative tag: Charanjit Singh's "Ten Ragas to a Disco Beat" is an
# Indian record played on a drum machine, and cosmic groove says more about it
# than beats & IDM does. Flip these two if that reads wrong.
GENRE_PRIORITY = ["jazz", "rap", "global", "electronic", "rock", "experimental"]

# Pitchfork's scraped era begins here; the Kaggle dump covers everything
# before it. The split is what separates the punk turn from the dad-rock shelf.
ROCK_ERA_CUTOFF = "2017-01-01"


def rock_cluster(modern):
    """Where a Pitchfork 'rock' review belongs.

    Rock is Pitchfork's widest bucket: Leonard Cohen and Big Thief share it.
    Reviews from the scraped era map to the punk turn, older ones to the
    dad/boomer-rock shelf. An unknown era takes the older reading, which is
    the safer default for a catalogue record.
    """
    return "punk-turn" if modern else "dad-rock"
