from __future__ import annotations

def create_views(con, table: str = "election_results") -> None:
    con.execute(f"""
        CREATE OR REPLACE VIEW vw_results_clean AS
        SELECT
            region,
            circonscription_code,
            circonscription_name,
            nb_bv,
            inscrits,
            votants,
            taux_participation,
            bull_nuls,
            suf_exprimes,
            bull_blancs_nbr,
            bull_blancs_percent,
            party,
            candidate,
            score,
            score_percent,
            elected
        FROM {table}
    """)

    # Turnout view: one row per circonscription
    con.execute("""
        CREATE OR REPLACE VIEW vw_turnout AS
        SELECT
            region,
            circonscription_code,
            circonscription_name,
            MAX(nb_bv) AS nb_bv,
            MAX(inscrits) AS inscrits,
            MAX(votants) AS votants,
            MAX(taux_participation) AS taux_participation,
            MAX(bull_nuls) AS bull_nuls,
            MAX(suf_exprimes) AS suf_exprimes,
            MAX(bull_blancs_nbr) AS bull_blancs_nbr,
            MAX(bull_blancs_percent) AS bull_blancs_percent
        FROM vw_results_clean
        GROUP BY 1,2,3
    """)

    # Winners view: use elected if present, otherwise fallback to max(score)
    con.execute("""
    CREATE OR REPLACE VIEW vw_winners AS
    SELECT
        region,
        circonscription_code,
        circonscription_name,
        nb_bv,
        inscrits,
        votants,
        taux_participation,
        bull_nuls,
        suf_exprimes,
        bull_blancs_nbr,
        bull_blancs_percent,
        party,
        candidate,
        score,
        score_percent,
        elected
    FROM (
        SELECT
            *,
            SUM(CASE WHEN elected THEN 1 ELSE 0 END)
              OVER (PARTITION BY circonscription_code) AS elected_count,
            MAX(score) OVER (PARTITION BY circonscription_code) AS max_score
        FROM vw_results_clean
    ) t
    WHERE
        (t.elected_count > 0 AND t.elected = TRUE)
        OR
        (t.elected_count = 0 AND t.score = t.max_score);
    """)

    # Seats by party
    con.execute("""
        CREATE OR REPLACE VIEW vw_party_seats AS
        SELECT party, COUNT(*) AS seats
        FROM vw_winners
        GROUP BY party
        ORDER BY seats DESC
    """)
