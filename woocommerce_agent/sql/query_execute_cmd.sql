create or replace function execute_sql(sql text)
returns setof jsonb
language plpgsql
as $$
begin
  return query execute sql;
end;
$$;
