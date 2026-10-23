# Audit commands: Java

`$FILES` = changed `.java` files (`git diff --name-only main...HEAD -- '*.java'`).
Patterns are POSIX ERE; run them with `/usr/bin/grep -E` (or GNU grep), not
an aliased grep with looser syntax. Every hit is a lead to read.

## Linters (if the project runs them)

Run the project's own configuration first (`mvn checkstyle:check pmd:check`,
`gradle checkstyleMain pmdMain`). For a one-off pass:

```bash
# Checkstyle: principles-checkstyle.xml lists NestedIfDepth, NestedForDepth,
# NestedTryDepth, CyclomaticComplexity, NPathComplexity, ParameterNumber,
# ClassFanOutComplexity, DesignForExtension, FinalClass, VisibilityModifier
java -jar checkstyle-<version>-all.jar -c principles-checkstyle.xml $FILES

# PMD 7
pmd check --no-cache -f text -d src/main/java -R \
  category/java/design.xml/AvoidDeeplyNestedIfStmts,category/java/design.xml/CognitiveComplexity,category/java/design.xml/CyclomaticComplexity,category/java/design.xml/MutableStaticState,category/java/bestpractices.xml/AbstractClassWithoutAbstractMethod
```

Minimal Checkstyle config: a `Checker` module containing a `TreeWalker` with
one `<module name="..."/>` per rule above. Unknown module names make
Checkstyle fail, so a typo cannot pass silently.

**Error Prone** (only if the build already has it as a `javac` plugin): add
`-Xep:JavaTimeDefaultTimeZone:ERROR` (`LocalDate.now()` without a zone or
`Clock`), `-Xep:FieldCanBeFinal:WARN` (off by default), `-Xep:OptionalEquality`,
`-Xep:ReturnValueIgnored`.

**ArchUnit** (as a test in the project), for rules that must hold, not leads:

```java
noClasses().that().resideInAPackage("..core..")
    .should().dependOnClassesThat().resideInAnyPackage("java.net.http..", "java.sql..");
noClasses().that().resideInAPackage("..core..")
    .should().callMethod(System.class, "currentTimeMillis")
    .orShould().callMethod(System.class, "getenv", String.class);
GeneralCodingRules.NO_CLASSES_SHOULD_USE_FIELD_INJECTION;
GeneralCodingRules.NO_CLASSES_SHOULD_ACCESS_STANDARD_STREAMS;
```

## Composition / DI

```bash
# Interfaces, then implementations of one (NAME): second implementation?
/usr/bin/grep -rnE '^[[:space:]]*(public[[:space:]]+)?(sealed[[:space:]]+)?interface[[:space:]]+[A-Z]' --include='*.java' .
/usr/bin/grep -rnE '(implements|extends)[^{]*[^A-Za-z0-9_]NAME([^A-Za-z0-9_]|$)' --include='*.java' .
/usr/bin/grep -rnE 'class[[:space:]]+[A-Za-z0-9_]+Impl[^A-Za-z0-9_]' --include='*.java' .   # FooImpl next to Foo

# Inheritance, stubbed overrides, protected state
/usr/bin/grep -rnE 'abstract[[:space:]]+class|class[[:space:]]+[A-Za-z0-9_<>]+[[:space:]]+extends[[:space:]]' --include='*.java' .
/usr/bin/grep -rn 'throw new UnsupportedOperationException' --include='*.java' .   # DrawableImage smell
/usr/bin/grep -rnE '^[[:space:]]*protected[[:space:]]+[^(]*[;=]' --include='*.java' .

# Static state and singletons
/usr/bin/grep -rnE '^[[:space:]]*([a-z]+[[:space:]]+)*static[[:space:]]+[^(]*[;=]' --include='*.java' . \
  | /usr/bin/grep -vE 'static final|:[0-9]+:import '
/usr/bin/grep -rnE 'static final[^=]*=[[:space:]]*new[[:space:]]+([a-z.]+\.)?(HashMap|ArrayList|HashSet|LinkedList|TreeMap|ConcurrentHashMap)' --include='*.java' .
/usr/bin/grep -rnE 'getInstance\(|^[[:space:]]*static[[:space:]]*\{' --include='*.java' .

# Field injection (annotation on its own line, field on the next)
/usr/bin/grep -rnE -A1 '^[[:space:]]*@(Autowired|Inject)[[:space:]]*$' --include='*.java' . \
  | /usr/bin/grep -E '^[^:]+-[0-9]+-[[:space:]]*(private|protected|public)?[^(]*;'

# IO, env and clock below the edge (adjust the core package path)
/usr/bin/grep -rnE '^import java\.(net|sql)\.|System\.(getenv|getProperty|currentTimeMillis)\(|(Instant|LocalDate|LocalDateTime|ZonedDateTime)\.now\(\)|HttpClient\.new|new (Random|Socket|FileInputStream|FileOutputStream)\(' --include='*.java' src/main/java/com/acme/core

# Service locator; tests that patch hardwired dependencies
/usr/bin/grep -rn 'getBean(' --include='*.java' src/main
/usr/bin/grep -rnE 'mockStatic\(|ReflectionTestUtils|@InjectMocks|setAccessible\(true\)|PowerMock' --include='*.java' src/test
```

Ordering: look for `void` methods that mutate the receiver followed by
accessors on the same class that return an empty collection or `null` when
the mutator has not run.

## Flat code

```bash
# else after return/throw/continue/break (the line before "} else" ends the if-branch)
/usr/bin/grep -nE -B1 '^[[:space:]]*\}[[:space:]]*else([[:space:]]+if)?[[:space:]]*[({]' $FILES \
  | /usr/bin/grep -E '^[^:]+-[0-9]+-[[:space:]]*(return|throw|continue|break)([[:space:]]|;)'
# Optional unwrapped as a null check, or taken as a parameter
/usr/bin/grep -nE '\.isPresent\(\)|Optional<[^>]+>[[:space:]]+[a-z][A-Za-z0-9]*[[:space:]]*[,)]' $FILES
```

`flat-code/scripts/nesting_depth.py` reads only `.py`, `.go`, `.ex` and
`.exs`; on Java files it reports nothing and exits 0. Do not record that as
a pass. Use Checkstyle `NestedIfDepth`/`NestedForDepth` and PMD
`CognitiveComplexity`, then read the deepest methods; neither if-rule counts
loops or `try`.

## Measure first

```bash
# Optimisations should come with benchmarks: added or existing ones
git diff main...HEAD -- '*.java' | /usr/bin/grep -nE '^\+.*@Benchmark'
/usr/bin/grep -rln '@Benchmark' --include='*.java' .
# Low-level tricks in the diff that need evidence
git diff main...HEAD -- '*.java' | /usr/bin/grep -nE '^\+.*(sun\.misc\.Unsafe|VarHandle|@Contended|ThreadLocal|parallelStream\(|-XX:)'
```

If a JMH benchmark covers the touched code, run it on both sides with the
same JDK and flags and compare `Score ± Error` (the `benchmarks` module path
is an example; use the project's):

```bash
mvn -q package -pl benchmarks && java -jar benchmarks/target/benchmarks.jar NAME -f 3 -rf json -rff /tmp/new.json
git worktree add --detach /tmp/audit-base main
(cd /tmp/audit-base && mvn -q package -pl benchmarks && java -jar benchmarks/target/benchmarks.jar NAME -f 3 -rf json -rff /tmp/old.json)
git worktree remove /tmp/audit-base
```

Use a worktree for the base, never `git stash`. Overlapping error intervals
mean no detectable difference.
