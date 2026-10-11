-- Objects that would be lost or broken by excluding legacy pgvecto.rs.
-- Include automatically owned array types/internal objects in the dependency set.
WITH RECURSIVE extension_objects(classid, objid) AS (
  SELECT d.classid, d.objid
  FROM pg_depend d JOIN pg_extension e ON e.oid = d.refobjid
  WHERE d.refclassid = 'pg_extension'::regclass
    AND e.extname = 'vectors' AND d.deptype = 'e'
  UNION
  SELECT d.classid, d.objid
  FROM pg_depend d JOIN extension_objects o
    ON d.refclassid = o.classid AND d.refobjid = o.objid
  WHERE d.deptype IN ('i', 'a')
)
SELECT coalesce(json_agg(DISTINCT pg_describe_object(d.classid, d.objid, d.objsubid)), '[]')
FROM pg_depend d JOIN extension_objects o
  ON d.refclassid = o.classid AND d.refobjid = o.objid
WHERE NOT EXISTS (
  SELECT 1 FROM extension_objects own
  WHERE own.classid = d.classid AND own.objid = d.objid
);
