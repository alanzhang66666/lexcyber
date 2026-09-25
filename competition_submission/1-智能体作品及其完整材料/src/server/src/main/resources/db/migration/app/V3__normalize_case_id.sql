CREATE OR REPLACE FUNCTION app.normalize_case_id() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.case_id := COALESCE(NEW.case_id, '');
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tasks_case_id ON app.tasks;
CREATE TRIGGER trg_tasks_case_id BEFORE INSERT OR UPDATE ON app.tasks
FOR EACH ROW EXECUTE FUNCTION app.normalize_case_id();
