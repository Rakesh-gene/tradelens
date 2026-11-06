FROM ontop/ontop:5.5.0@sha256:d19a2055b02812c8ecc0a00cca1733c1669c4143dfeb728acbfdff92b45e94d7
# Keep the driver in the dedicated JDBC directory used by Ontop's launcher.
ADD --checksum=sha256:2a32a9dcbc42d67a50ad3a0de5efd102c8d2be46720045f2cbd6689f160ab7c7 https://repo.maven.apache.org/maven2/org/postgresql/postgresql/42.7.8/postgresql-42.7.8.jar /opt/ontop/jdbc/postgresql-42.7.8.jar
USER root
RUN chmod 755 /opt/ontop/jdbc && chmod 644 /opt/ontop/jdbc/postgresql-42.7.8.jar
USER ontop
COPY src/backend/ontology/tradelens.ttl src/backend/ontology/facts.ttl /opt/ontop/input/
COPY src/backend/repositories/semantic/tradelens.r2rml.ttl /opt/ontop/input/
COPY src/backend/repositories/semantic/lenses.json /opt/ontop/input/
COPY infra/ontology/ontop.properties /opt/ontop/input/
