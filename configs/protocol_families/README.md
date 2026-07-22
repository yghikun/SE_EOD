# Protocol Families

A protocol family contains reusable filesystem-independent semantics:

```text
abstract roles
abstract actions and lifecycle transitions
correctness obligations
applicability conditions
```

It must not contain Linux filesystem API names, concrete entry functions, or
known bug locations. A family says what legal completion means, not how one
filesystem spells an event.

Family schema v1 currently supports a single effect lifecycle package. More
complex Protocol A-C semantics remain in flat runtime configurations until the
package schema can represent them without losing behavior.
