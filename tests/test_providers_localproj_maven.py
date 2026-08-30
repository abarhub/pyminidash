from pathlib import Path

from pyminidash.providers.localproj.maven import parse_maven

NS = 'xmlns="http://maven.apache.org/POM/4.0.0"'


def _pom(dir: Path, body: str, name: str = "pom.xml"):
    (dir / name).write_text(
        f'<?xml version="1.0"?>\n<project {NS}>\n{body}\n</project>',
        encoding="utf-8")


def test_gav_and_name(tmp_path):
    _pom(tmp_path, """
      <groupId>com.example</groupId>
      <artifactId>app</artifactId>
      <version>1.4.0</version>
      <name>Mon Appli</name>
    """)
    info = parse_maven(tmp_path, [])
    assert info.readable is True
    assert (info.group_id, info.artifact_id, info.version) == (
        "com.example", "app", "1.4.0")
    assert info.name == "Mon Appli"


def test_group_and_version_inherited_from_parent(tmp_path):
    _pom(tmp_path, """
      <parent>
        <groupId>com.example</groupId>
        <artifactId>parent</artifactId>
        <version>3.2.1</version>
      </parent>
      <artifactId>child</artifactId>
    """)
    info = parse_maven(tmp_path, [])
    assert info.group_id == "com.example"
    assert info.version == "3.2.1"
    assert info.parent_gav == "com.example:parent:3.2.1"


def test_property_interpolation(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId>
      <version>1.0</version>
      <properties><java.version>17</java.version></properties>
      <dependencies>
        <dependency>
          <groupId>com.google.guava</groupId>
          <artifactId>guava</artifactId>
          <version>${guava.version}</version>
        </dependency>
      </dependencies>
    """)
    # ${guava.version} non défini -> laissé littéral
    info = parse_maven(tmp_path, ["guava"])
    assert info.java_version == "17"
    assert info.libs == (("guava", "${guava.version}"),)


def test_parent_on_disk_properties_merge(tmp_path):
    parent = tmp_path / "parent"
    child = tmp_path / "parent" / "svc"
    child.mkdir(parents=True)
    _pom(parent, """
      <groupId>g</groupId><artifactId>p</artifactId><version>1</version>
      <properties><spring.version>6.1.2</spring.version></properties>
    """)
    _pom(child, """
      <parent>
        <groupId>g</groupId><artifactId>p</artifactId><version>1</version>
        <relativePath>../pom.xml</relativePath>
      </parent>
      <artifactId>svc</artifactId>
      <dependencies>
        <dependency>
          <groupId>org.springframework</groupId>
          <artifactId>spring-core</artifactId>
          <version>${spring.version}</version>
        </dependency>
      </dependencies>
    """)
    info = parse_maven(child, ["spring-core"])
    assert info.libs == (("spring-core", "6.1.2"),)


def test_java_version_from_compiler_plugin(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <build><plugins><plugin>
        <artifactId>maven-compiler-plugin</artifactId>
        <configuration><release>21</release></configuration>
      </plugin></plugins></build>
    """)
    assert parse_maven(tmp_path, []).java_version == "21"


def test_spring_boot_from_starter_parent(tmp_path):
    _pom(tmp_path, """
      <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.1</version>
      </parent>
      <artifactId>a</artifactId>
    """)
    assert parse_maven(tmp_path, []).spring_boot_version == "3.2.1"


def test_spring_boot_from_dependency_management(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <dependencyManagement><dependencies><dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-dependencies</artifactId>
        <version>3.1.5</version>
      </dependency></dependencies></dependencyManagement>
    """)
    assert parse_maven(tmp_path, []).spring_boot_version == "3.1.5"


def test_modules_list(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <modules><module>core</module><module>web</module></modules>
    """)
    assert parse_maven(tmp_path, []).modules == ("core", "web")


def test_libs_present_and_absent(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <dependencies><dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId><version>3.14.0</version>
      </dependency></dependencies>
    """)
    info = parse_maven(tmp_path, ["commons-lang3", "guava"])
    assert info.libs == (("commons-lang3", "3.14.0"),)


def test_frontend_maven_plugin(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <build><plugins><plugin>
        <groupId>com.github.eirslett</groupId>
        <artifactId>frontend-maven-plugin</artifactId>
        <version>1.15.0</version>
        <configuration>
          <nodeVersion>v20.11.0</nodeVersion>
          <npmVersion>10.2.4</npmVersion>
        </configuration>
      </plugin></plugins></build>
    """)
    info = parse_maven(tmp_path, [])
    assert info.frontend_plugin_version == "1.15.0"
    assert info.frontend_node_version == "v20.11.0"
    assert info.frontend_npm_version == "10.2.4"


def test_angular_subscan(tmp_path):
    _pom(tmp_path, "<artifactId>a</artifactId><version>1</version>")
    front = tmp_path / "src" / "main" / "webapp"
    front.mkdir(parents=True)
    (front / "package.json").write_text(
        '{"dependencies": {"@angular/core": "17.1.0"}}', encoding="utf-8")
    assert parse_maven(tmp_path, []).angular_version == "17.1.0"


def test_libs_ignores_plugin_and_profile_deps_and_dedups(tmp_path):
    # C3 : _all_deps ne doit matcher QUE <dependencies> projet + <dependencyManagement>,
    # pas plugin/profile ; dédup par artifactId, version concrète > "managed".
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <build><plugins><plugin>
        <artifactId>some-plugin</artifactId>
        <dependencies><dependency>
          <groupId>x</groupId><artifactId>thelib</artifactId><version>9.9.9</version>
        </dependency></dependencies>
      </plugin></plugins></build>
      <profiles><profile><id>p</id><dependencies><dependency>
        <groupId>x</groupId><artifactId>thelib</artifactId><version>8.8.8</version>
      </dependency></dependencies></profile></profiles>
      <dependencies><dependency>
        <groupId>x</groupId><artifactId>thelib</artifactId>
      </dependency></dependencies>
      <dependencyManagement><dependencies><dependency>
        <groupId>x</groupId><artifactId>thelib</artifactId><version>1.2.3</version>
      </dependency></dependencies></dependencyManagement>
    """)
    info = parse_maven(tmp_path, ["thelib"])
    assert info.libs == (("thelib", "1.2.3"),)


def test_seeds_project_artifactId_property(tmp_path):
    # Minor maven : builtin project.artifactId disponible pour l'interpolation.
    _pom(tmp_path, """
      <artifactId>myart</artifactId><version>1</version>
      <dependencies><dependency>
        <groupId>x</groupId><artifactId>guava</artifactId>
        <version>${project.artifactId}</version>
      </dependency></dependencies>
    """)
    info = parse_maven(tmp_path, ["guava"])
    assert info.libs == (("guava", "myart"),)


def test_malformed_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("<project><broken", encoding="utf-8")
    info = parse_maven(tmp_path, [])
    assert info.readable is False
    assert info.artifact_id is None
