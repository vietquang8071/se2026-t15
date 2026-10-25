-- Chỉ áp dụng trong database/container test riêng, không phải migration repo gốc.
CREATE SCHEMA ad060;
CREATE TABLE ad060.meetings (id text PRIMARY KEY, owner_id text NOT NULL);
CREATE TABLE ad060.revisions (
  meeting_id text NOT NULL REFERENCES ad060.meetings(id),
  source_id text NOT NULL,
  external_id text NOT NULL,
  segments jsonb NOT NULL CHECK (jsonb_typeof(segments) = 'array'),
  PRIMARY KEY (meeting_id, source_id, external_id)
);
INSERT INTO ad060.meetings VALUES ('m1', 'son');
CREATE FUNCTION ad060.store_revision(mid text, actor text, src text, eid text, seg jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE actual_owner text; old_segments jsonb; inserted_count integer;
BEGIN
  SELECT owner_id INTO actual_owner FROM ad060.meetings WHERE id = mid FOR SHARE;
  IF NOT FOUND THEN RETURN '{"status":404,"body":{"code":"MEETING_NOT_FOUND"}}'; END IF;
  IF actor <> actual_owner THEN RETURN '{"status":403,"body":{"code":"FORBIDDEN"}}'; END IF;
  INSERT INTO ad060.revisions VALUES(mid,src,eid,seg) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS inserted_count = ROW_COUNT;
  IF inserted_count = 1 THEN RETURN '{"status":201,"body":{"code":"IMPORTED"}}'; END IF;
  SELECT segments INTO old_segments FROM ad060.revisions
    WHERE meeting_id=mid AND source_id=src AND external_id=eid;
  IF old_segments <> seg THEN RETURN '{"status":409,"body":{"code":"IDEMPOTENCY_CONFLICT"}}'; END IF;
  RETURN '{"status":200,"body":{"code":"ALREADY_IMPORTED"}}';
END $$;
