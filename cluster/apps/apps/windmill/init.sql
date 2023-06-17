CREATE ROLE windmill_user;

-- TODO: is this safe??
GRANT ALL
ON ALL TABLES IN SCHEMA public 
TO windmill_user;

GRANT ALL PRIVILEGES 
ON ALL SEQUENCES IN SCHEMA public 
TO windmill_user;

ALTER DEFAULT PRIVILEGES 
    IN SCHEMA public
    GRANT ALL ON TABLES TO windmill_user;

ALTER DEFAULT PRIVILEGES 
    IN SCHEMA public
    GRANT ALL ON SEQUENCES TO windmill_user;


CREATE ROLE windmill_admin WITH BYPASSRLS;

GRANT ALL
ON ALL TABLES IN SCHEMA public 
TO windmill_admin;

GRANT ALL PRIVILEGES 
ON ALL SEQUENCES IN SCHEMA public 
TO windmill_admin;

ALTER DEFAULT PRIVILEGES 
    IN SCHEMA public
    GRANT ALL ON TABLES TO windmill_admin;

ALTER DEFAULT PRIVILEGES 
    IN SCHEMA public
    GRANT ALL ON SEQUENCES TO windmill_admin;

GRANT windmill_admin TO windmill;
GRANT windmill_user TO windmill;
