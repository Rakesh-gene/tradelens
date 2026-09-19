"""Bounded sector aggregates and database-ranked constituent queries."""

ROTATION_CTE = """WITH sessions AS (
    SELECT DISTINCT trading_date FROM technical_features
    WHERE trading_date <= %(as_of)s ORDER BY trading_date DESC LIMIT %(session_count)s
), dates AS (
    SELECT trading_date AS current_date FROM sessions
), members AS (
    SELECT DISTINCT m.sector_code, s.name AS sector_name, e.isin, e.symbol,
           e.company_name, d.current_date AS data_as_of,
           f.relative_strength_1m, f.relative_strength_3m,
           f.relative_strength_6m, f.relative_strength_12m,
           f.relative_strength_3m / 3 AS baseline_rs,
           f.feature_version, f.data_version
    FROM dates d
    JOIN security_sector_memberships m ON m.effective_from <= d.current_date
      AND (m.effective_to IS NULL OR m.effective_to >= d.current_date)
    JOIN market_sectors s ON s.code = m.sector_code
    JOIN nse_equities e ON e.isin = m.isin AND e.series = 'EQ'
    LEFT JOIN LATERAL (
        SELECT * FROM technical_features f WHERE f.isin = e.isin
          AND f.trading_date = d.current_date
        ORDER BY f.generated_at DESC, f.feature_version DESC LIMIT 1
    ) f ON TRUE
)
"""


class SectorRotationQueries:
    def sector_rotation_rows(self, as_of):
        return self._rotation_rows(as_of, 1)

    def sector_rotation_history_rows(self, as_of, sessions=5):
        return self._rotation_rows(as_of, sessions)

    def _rotation_rows(self, as_of, session_count):
        return self._fetch_all(ROTATION_CTE + """
            SELECT sector_code, sector_name, data_as_of,
                   COUNT(*) AS member_count, COUNT(relative_strength_3m) AS covered_count,
                   ARRAY_AGG(DISTINCT feature_version) FILTER (WHERE feature_version IS NOT NULL) AS feature_versions,
                   ARRAY_AGG(DISTINCT data_version) FILTER (WHERE data_version IS NOT NULL) AS adjustment_versions,
                   COUNT(relative_strength_1m) FILTER (WHERE relative_strength_3m IS NOT NULL) AS paired_count,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY relative_strength_1m) AS rs_1m,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY relative_strength_3m) AS rs_3m,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY relative_strength_6m) AS rs_6m,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY relative_strength_12m) AS rs_12m,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY relative_strength_1m)
                     FILTER (WHERE baseline_rs IS NOT NULL) AS short_rs,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY baseline_rs)
                     FILTER (WHERE relative_strength_1m IS NOT NULL) AS baseline_rs
            FROM members GROUP BY sector_code, sector_name, data_as_of
            ORDER BY rs_3m DESC NULLS LAST, sector_code
        """, {"as_of": as_of, "session_count": session_count})

    def sector_strength_stocks(self, as_of, sector, limit, offset):
        return self._fetch_all(ROTATION_CTE + """
            SELECT *, ROW_NUMBER() OVER (ORDER BY relative_strength_3m DESC NULLS LAST, isin) AS rank
            FROM members WHERE sector_code = %(sector)s
            ORDER BY relative_strength_3m DESC NULLS LAST, isin
            LIMIT %(limit)s OFFSET %(offset)s
        """, {"as_of": as_of, "session_count": 1, "sector": sector, "limit": limit + 1, "offset": offset})


class MemorySectorRotationQueries:
    def _sector_members(self, as_of):
        from datetime import date
        dates = sorted({f["trading_date"] for f in self.features if f["trading_date"] <= as_of}, reverse=True)
        if not dates:
            return []
        return self._sector_members_on(dates[0])

    def _sector_members_on(self, current):
        from datetime import date
        members = []
        for security in self.securities.values():
            start = security.get("effective_from", date.min)
            end = security.get("effective_to")
            if not security.get("sector_code") or security.get("series", "EQ") != "EQ" or start > current or (end and end < current):
                continue
            features = [f for f in self.features if f["isin"] == security["isin"] and f["trading_date"] == current]
            feature = max(features, key=lambda f: (str(f.get("generated_at", "")), f.get("feature_version", "")), default={})
            rs = feature.get("relative_strength_3m")
            members.append({**security, **feature, "data_as_of": current, "baseline_rs": float(rs) / 3 if rs is not None else None})
        return members

    def sector_rotation_rows(self, as_of):
        return self._rotation_rows(self._sector_members(as_of))

    def sector_rotation_history_rows(self, as_of, sessions=5):
        dates = sorted({f["trading_date"] for f in self.features if f["trading_date"] <= as_of}, reverse=True)[:sessions]
        return [row for current in dates for row in self._rotation_rows(self._sector_members_on(current))]

    @staticmethod
    def _rotation_rows(members):
        from statistics import median
        result = []
        for code in sorted({m["sector_code"] for m in members}):
            cohort = [m for m in members if m["sector_code"] == code]
            paired = [m for m in cohort if m.get("relative_strength_3m") is not None and m.get("relative_strength_1m") is not None]
            def middle(rows, key):
                values = [float(m[key]) for m in rows if m.get(key) is not None]
                return median(values) if values else None
            result.append({"sector_code": code, "sector_name": cohort[0].get("sector_name", code),
                           "data_as_of": cohort[0]["data_as_of"], 
                           "member_count": len(cohort), "covered_count": sum(m.get("relative_strength_3m") is not None for m in cohort),
                           "feature_versions": sorted({m["feature_version"] for m in cohort if m.get("feature_version")}),
                           "adjustment_versions": sorted({m["data_version"] for m in cohort if m.get("data_version")}),
                           "paired_count": len(paired), "short_rs": middle(paired, "relative_strength_1m"),
                           "baseline_rs": middle(paired, "baseline_rs"),
                           **{f"rs_{h}": middle(cohort, f"relative_strength_{h}") for h in ("1m", "3m", "6m", "12m")}})
        return sorted(result, key=lambda r: (r["rs_3m"] is None, -(r["rs_3m"] or 0), r["sector_code"]))

    def sector_strength_stocks(self, as_of, sector, limit, offset):
        rows = sorted((m for m in self._sector_members(as_of) if m["sector_code"] == sector),
                      key=lambda m: (m.get("relative_strength_3m") is None, -(m.get("relative_strength_3m") or 0), m["isin"]))
        return [{**row, "rank": index + 1} for index, row in enumerate(rows)][offset:offset + limit + 1]
