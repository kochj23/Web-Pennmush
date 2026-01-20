

# Web-Pennmush Softcode Reference Guide

**Complete documentation of the MUSHcode scripting language**

Version: 3.0.0
Author: Jordan Koch
Last Updated: January 20, 2026

---

## Table of Contents

1. [Introduction](#introduction)
2. [Syntax Overview](#syntax-overview)
3. [Substitutions](#substitutions)
4. [Current Functions (30)](#current-functions)
5. [Missing Functions (Critical)](#missing-functions)
6. [Comparison with PennMUSH](#comparison-with-pennmush)
7. [Advanced Examples](#advanced-examples)
8. [Best Practices](#best-practices)
9. [Performance Considerations](#performance-considerations)

---

## Introduction

Softcode (MUSHcode) is a programming language embedded in Web-Pennmush that allows players to create dynamic, interactive content. Functions are evaluated using square bracket syntax: `[function(args)]`.

### What Can You Do With Softcode?

- Create dynamic object descriptions
- Build interactive puzzles and games
- Automate repetitive tasks
- Create smart objects that respond to events
- Build complex game mechanics
- Process player input
- Generate random content

---

## Syntax Overview

### Function Calls
```
[function(arg1, arg2, arg3)]
```

### Nested Evaluation
```
[add([mul(5, 3)], 10)]
# Evaluates inner first: [mul(5,3)] = 15
# Then outer: [add(15, 10)] = 25
```

### Substitutions
```
%0-%9   - Arguments passed to softcode
%#      - Executor's object ID
%%      - Literal % character
```

### Attribute References
```
v(ATTR)         - Get attribute from executor object
get(#123/ATTR)  - Get attribute from object #123
```

### Object References
```
#123    - Reference to object ID 123
```

---

## Substitutions

| Substitution | Description | Example |
|--------------|-------------|---------|
| `%0-%9` | Arguments 1-10 | `%0` = first argument |
| `%#` | Executor's object ID | If executor is #42, `%#` = 42 |
| `%%` | Literal percent sign | `%%` displays as `%` |
| `v(ATTR)` | Get attribute from executor | `v(HP)` gets executor's HP |
| `get(OBJ/ATTR)` | Get attribute from object | `get(#5/HP)` gets object #5's HP |

### Example
```
@set sword=ON_HIT:You deal [v(DAMAGE)] damage to the enemy!
# When triggered, if sword has DAMAGE:50, outputs:
# "You deal 50 damage to the enemy!"
```

---

## Current Functions (30)

### String Functions (6)

#### strlen(string)
Returns the length of a string.
```
think [strlen(Hello)]
# Output: 5

think [strlen(Hello World)]
# Output: 11
```

#### strcat(str1, str2, ...)
Concatenates multiple strings.
```
think [strcat(Hello, " ", World)]
# Output: Hello World

@set sword=FULL_NAME:[strcat([v(PREFIX)], " ", [v(NAME)])]
```

#### substr(string, start, length)
Extracts a substring.
```
think [substr(Hello World, 0, 5)]
# Output: Hello

think [substr(Hello World, 6, 5)]
# Output: World
```

#### trim(string)
Removes leading and trailing whitespace.
```
think [trim(  Hello  )]
# Output: Hello
```

#### ucstr(string)
Converts string to uppercase.
```
think [ucstr(hello world)]
# Output: HELLO WORLD
```

#### lcstr(string)
Converts string to lowercase.
```
think [lcstr(HELLO WORLD)]
# Output: hello world
```

---

### Math Functions (6)

#### add(num1, num2, ...)
Adds numbers.
```
think [add(10, 20, 30)]
# Output: 60

@set player=TOTAL_HP:[add([v(BASE_HP)], [v(BONUS_HP)])]
```

#### sub(num1, num2, ...)
Subtracts numbers (left to right).
```
think [sub(100, 25, 10)]
# Output: 65 (100 - 25 - 10)
```

#### mul(num1, num2, ...)
Multiplies numbers.
```
think [mul(5, 10, 2)]
# Output: 100

@set sword=DAMAGE:[mul([v(BASE_DAMAGE)], [v(LEVEL)])]
```

#### div(num1, num2, ...)
Divides numbers (left to right).
```
think [div(100, 5, 2)]
# Output: 10 (100 / 5 / 2)

# Division by zero returns infinity
think [div(10, 0)]
# Output: inf
```

#### mod(num1, num2)
Modulo operation (remainder).
```
think [mod(17, 5)]
# Output: 2

# Useful for cycling
@set teleporter=DEST:[add(100, [mod([v(COUNTER)], 5)])]
# Cycles between rooms #100-#104
```

#### rand(max, min)
Generates random number.
```
think [rand(100)]
# Output: Random number 0-100

think [rand(20, 1)]
# Output: Random number 1-20

# Random loot drop
@set chest=GOLD:[rand(100, 10)]
```

---

### Logic Functions (9)

#### eq(val1, val2)
Equality comparison. Returns 1 if equal, 0 if not.
```
think [eq(5, 5)]
# Output: 1

think [eq(hello, world)]
# Output: 0

@set door=LOCKED:[eq([v(KEY_ID)], %#)]
# Locked if key holder's ID equals current player
```

#### neq(val1, val2)
Not equal comparison.
```
think [neq(5, 10)]
# Output: 1
```

#### gt(num1, num2)
Greater than.
```
think [gt(10, 5)]
# Output: 1

@set door=CAN_ENTER:[gt([get(%#/HP)], 50)]
# Player can enter if HP > 50
```

#### gte(num1, num2)
Greater than or equal.
```
think [gte(10, 10)]
# Output: 1
```

#### lt(num1, num2)
Less than.
```
think [lt(5, 10)]
# Output: 1
```

#### lte(num1, num2)
Less than or equal.
```
think [lte(5, 5)]
# Output: 1
```

#### and(val1, val2, ...)
Logical AND. Returns 1 if all values are truthy.
```
think [and(1, 1, 1)]
# Output: 1

think [and(1, 0, 1)]
# Output: 0

@set quest=COMPLETE:[and([get(%#/STEP1)], [get(%#/STEP2)], [get(%#/STEP3)])]
```

#### or(val1, val2, ...)
Logical OR. Returns 1 if any value is truthy.
```
think [or(0, 1, 0)]
# Output: 1
```

#### not(val)
Logical NOT. Returns 1 if value is falsy.
```
think [not(0)]
# Output: 1

think [not(1)]
# Output: 0
```

---

### Conditional Functions (3)

#### if(condition, true_value)
Returns true_value if condition is truthy.
```
think [if(1, Yes)]
# Output: Yes

think [if(0, Yes)]
# Output: (empty)

@set door=MESSAGE:[if([v(LOCKED)], This door is locked.)]
```

#### ifelse(condition, true_value, false_value)
Returns true_value if condition is truthy, false_value otherwise.
```
think [ifelse(1, Yes, No)]
# Output: Yes

think [ifelse(0, Yes, No)]
# Output: No

@set sword=STATUS:[ifelse([v(BROKEN)], BROKEN, FUNCTIONAL)]
```

#### switch(value, case1, result1, case2, result2, ..., default)
Multi-way branch.
```
think [switch(2, 1, one, 2, two, 3, three, other)]
# Output: two

@set npc=GREETING:[switch([v(MOOD)], happy, Hello friend!, angry, Go away!, neutral, Greetings.)]
```

---

### Object Functions (6)

#### name(objid)
Gets the name of an object.
```
think [name(#0)]
# Output: Room Zero

@set sign=TEXT:Welcome to [name([loc(%#)])]
# "Welcome to Central Plaza"
```

#### num(objname)
Gets the object ID by name.
```
think [num(Room Zero)]
# Output: #0

think [num(NonExistent)]
# Output: #-1
```

#### loc(objid)
Gets the location of an object.
```
think [loc(#5)]
# Output: #2 (if magic crystal is in Central Plaza)

@set teleporter=DEST:[loc(%#)]
# Remembers where player came from
```

#### owner(objid)
Gets the owner of an object.
```
think [owner(#5)]
# Output: #1 (God owns magic crystal)
```

#### get(obj/attr)
Gets an attribute from an object.
```
think [get(#5/POWER)]
# Output: 10 (magic crystal's power)

@set spell=DAMAGE:[mul([get(%#/MAGIC_LEVEL)], 5)]
```

#### v(attr)
Gets an attribute from the executor object.
```
@set me=HP:100
think [v(HP)]
# Output: 100

@set sword=DESCRIPTION:This sword glows with [v(ELEMENT)] energy.
```

---

### List Functions (4)

#### words(string)
Counts words in a string.
```
think [words(Hello World Test)]
# Output: 3
```

#### first(string)
Gets the first word.
```
think [first(Hello World)]
# Output: Hello
```

#### rest(string)
Gets all but the first word.
```
think [rest(Hello World Test)]
# Output: World Test
```

#### last(string)
Gets the last word.
```
think [last(Hello World Test)]
# Output: Test
```

---

## Missing Functions (Critical)

### Current: 30 functions
### PennMUSH has: 500+ functions

### High Priority Missing Functions

#### String Manipulation (20+ missing)
- `mid()` - Middle of string (better substr)
- `left()` - Left N characters
- `right()` - Right N characters
- `repeat()` - Repeat string N times
- `reverse()` - Reverse string
- `scramble()` - Randomize characters
- `space()` - N spaces
- `center()` - Center text
- `ljust()`, `rjust()` - Justify text
- `edit()` - Edit string with patterns
- `escape()`, `unescape()` - HTML/special chars
- `secure()` - Make string safe
- `stripansi()` - Remove ANSI codes
- `ansi()` - Add ANSI color codes
- `capstr()` - Capitalize
- `titlestr()` - Title Case
- `art()` - A/an article selection
- `alphamax()`, `alphamin()` - Alphabetical comparison
- `comp()` - String comparison
- `strmatch()` - Wildcard matching

#### List Functions (30+ missing)
- `lnum()` - Generate number list
- `ldelete()` - Remove from list
- `linsert()` - Insert into list
- `lreplace()` - Replace list element
- `extract()` - Extract range from list
- `merge()` - Merge two lists
- `setdiff()` - List difference
- `setinter()` - List intersection
- `setunion()` - List union
- `sort()` - Sort list
- `sortby()` - Sort with comparison function
- `shuffle()` - Randomize list
- `splice()` - Combine lists
- `filter()` - Filter list elements
- `filterbool()` - Filter by boolean
- `fold()` - Reduce list to value
- `map()` - Transform list elements
- `iter()` - Iterate over list
- `parse()` - Split and process
- `unique()` - Remove duplicates
- `elements()` - Get specific elements
- `member()` - Check membership
- `lpos()` - Find position

#### Math Functions (20+ missing)
- `abs()` - Absolute value
- `sign()` - Sign of number
- `min()`, `max()` - Min/max values
- `ceil()`, `floor()` - Ceiling/floor
- `round()` - Rounding
- `trunc()` - Truncate
- `sqrt()` - Square root
- `power()` - Exponentiation
- `log()`, `ln()` - Logarithms
- `exp()` - Exponential
- `sin()`, `cos()`, `tan()` - Trigonometry
- `asin()`, `acos()`, `atan()` - Inverse trig
- `pi()` - Pi constant
- `e()` - Euler's number
- `mean()` - Average
- `median()` - Median value
- `stddev()` - Standard deviation
- `bound()` - Clamp value
- `inc()`, `dec()` - Increment/decrement

#### Object/Database (15+ missing)
- `contents()` - List object contents
- `exits()` - List exits
- `lexits()` - List exits formatted
- `con()` - Contents count
- `exits()` - Exit list
- `home()` - Get home location
- `parent()` - Get parent object
- `zone()` - Get zone
- `type()` - Get object type
- `flags()` - Get object flags
- `hasflag()` - Check flag
- `hasattr()` - Check attribute existence
- `hasattrp()` - Check attribute with value
- `lattr()` - List attributes
- `attrs()` - Attribute count

#### Database Search (10+ missing)
- `search()` - Search database
- `lsearch()` - Attribute search
- `children()` - Get child objects
- `lcon()` - Formatted contents
- `lobjects()` - List objects
- `nearby()` - Objects in vicinity
- `followers()` - Following objects
- `following()` - Leader object

#### Time/Date (10+ missing)
- `time()` - Current timestamp
- `secs()` - Seconds since epoch
- `convsecs()` - Convert to readable
- `etimefmt()` - Format elapsed time
- `timefmt()` - Format timestamp
- `isdaylight()` - Daylight saving?
- `starttime()` - Server start time
- `restarts()` - Restart count

#### Logic/Flow (5+ missing)
- `case()` - Case statement
- `t()` - Boolean test
- `default()` - Default value
- `null()` - Return null
- `squish()` - Remove extra whitespace

#### Database Manipulation (5+ missing)
- `create()` - Create object
- `clone()` - Clone object
- `set()` - Set attribute
- `wipe()` - Clear attributes
- `mvattr()` - Move attribute

#### Permission/Lock (5+ missing)
- `elock()` - Evaluate lock
- `lock()` - Get lock key
- `visible()` - Check visibility
- `controls()` - Check control permission
- `cansee()` - Line of sight check

#### Formatting (10+ missing)
- `table()` - Format as table
- `columns()` - Columnar layout
- `align()` - Align numbers
- `ljust()`, `rjust()`, `center()` - Text alignment
- `repeat()` - Repeat string
- `translate()` - Character mapping
- `textfile()` - Read text file

#### Advanced (10+ missing)
- `foreach()` - Iterate with action
- `munge()` - Complex text processing
- `regedit()` - Regex editing
- `regmatch()` - Regex matching
- `sql()` - SQL queries (if enabled)
- `eval()` - Evaluate code string
- `ulocal()` - Call user function
- `u()` - Function call shorthand

---

## Current Functions (Detailed Reference)

### STRING FUNCTIONS

#### strlen(string)
**Returns**: Integer (length of string)
**Arguments**: string
**Description**: Returns the character count of the input string.

**Examples**:
```
[strlen(Hello)]              → 5
[strlen(Hello World)]        → 11
[strlen(]                    → 0
[strlen(   spaces   )]       → 13 (includes spaces)
```

**Use Cases**:
- Validate input length
- Truncate strings
- Calculate padding

**Code**:
```
@set validator=CHECK:[if([gt([strlen([v(NAME)])], 20)], Name too long)]
```

---

#### strcat(str1, str2, ...)
**Returns**: String (concatenated result)
**Arguments**: Multiple strings
**Description**: Joins all arguments into a single string.

**Examples**:
```
[strcat(Hello, World)]                    → HelloWorld
[strcat(Hello, " ", World)]               → Hello World
[strcat([v(FIRST)], " ", [v(LAST)])]      → John Doe (if attributes set)
```

**Use Cases**:
- Build complex strings
- Combine attribute values
- Construct descriptions

**Code**:
```
@set sword=FULL_DESC:[strcat(A [v(MATERIAL)] sword with [v(ENCHANTMENT)] powers.)]
```

---

#### substr(string, start, length)
**Returns**: String (substring)
**Arguments**: string (text), start (index), length (chars to extract)
**Description**: Extracts a portion of the string starting at index.

**Examples**:
```
[substr(Hello World, 0, 5)]      → Hello
[substr(Hello World, 6, 5)]      → World
[substr(Hello World, 0, 100)]    → Hello World (length capped)
```

**Use Cases**:
- Extract portions of text
- Parse formatted strings
- Truncate display

**Code**:
```
@set item=SHORT_DESC:[substr([v(DESCRIPTION)], 0, 50)]...
```

---

#### trim(string)
**Returns**: String (trimmed)
**Arguments**: string
**Description**: Removes leading and trailing whitespace.

**Examples**:
```
[trim(  Hello  )]       → Hello
[trim(
  Multiline
)]                      → Multiline
```

**Use Cases**:
- Clean user input
- Normalize spacing
- Format output

---

#### ucstr(string) / lcstr(string)
**Returns**: String (case-converted)
**Arguments**: string
**Description**: Converts to uppercase or lowercase.

**Examples**:
```
[ucstr(hello)]         → HELLO
[lcstr(WORLD)]         → world
```

**Use Cases**:
- Case-insensitive comparison
- Formatting
- Display emphasis

---

### MATH FUNCTIONS

#### add/sub/mul/div(numbers...)
**Returns**: Number (result)
**Arguments**: Multiple numbers
**Description**: Basic arithmetic operations.

**Examples**:
```
[add(10, 20, 30)]         → 60
[sub(100, 25)]            → 75
[mul(5, 10)]              → 50
[div(100, 5)]             → 20
```

**Use Cases**:
- HP calculations
- Damage formulas
- Resource management
- Currency conversions

**Advanced Example**:
```
@set weapon=ATTACK_ROLL:[add([rand(20, 1)], [v(BONUS)], [div([get(%#/STR)], 2)])]
# Rolls 1d20 + weapon bonus + (player strength / 2)
```

---

#### mod(num1, num2)
**Returns**: Integer (remainder)
**Arguments**: dividend, divisor
**Description**: Returns remainder of division.

**Examples**:
```
[mod(17, 5)]              → 2
[mod(20, 3)]              → 2
```

**Use Cases**:
- Cycling through values
- Even/odd detection
- Wrap-around indexing

**Example**:
```
@set clock=HOUR:[mod([secs()], 24)]
@set cycle=PHASE:[mod([v(COUNTER)], 4)]
```

---

#### rand(max, min)
**Returns**: Integer (random number)
**Arguments**: max (required), min (optional, default 0)
**Description**: Generates random number in range.

**Examples**:
```
[rand(100)]               → Random 0-100
[rand(20, 1)]             → Random 1-20
[rand(6, 1)]              → Dice roll (1d6)
```

**Use Cases**:
- Dice rolls
- Random loot
- Procedural generation
- NPC behavior

**Advanced Examples**:
```
# 3d6 dice roll
[add([rand(6,1)], [rand(6,1)], [rand(6,1)])]

# Random treasure
@set chest=GOLD:[mul([rand(10, 1)], 10)]
```

---

### LOGIC FUNCTIONS

All logic functions return `1` (true) or `0` (false).

**Comparison Functions**:
- `eq(a, b)` - a == b
- `neq(a, b)` - a != b
- `gt(a, b)` - a > b
- `gte(a, b)` - a >= b
- `lt(a, b)` - a < b
- `lte(a, b)` - a <= b

**Boolean Functions**:
- `and(a, b, ...)` - All truthy
- `or(a, b, ...)` - Any truthy
- `not(a)` - Inverts

**Use Cases**: Conditions, locks, validation, game logic

---

### CONDITIONAL FUNCTIONS

#### if/ifelse/switch
Used for branching logic.

**Complex Example**:
```
@set door=ACCESS_MESSAGE:[switch(
  [v(STATE)],
  locked, [ifelse([eq(%#, [v(KEY_HOLDER)])], Click! The door unlocks., The door is locked.)],
  open, The door is open.,
  broken, The door is broken off its hinges.
)]
```

---

### OBJECT FUNCTIONS

#### name/num/loc/owner
Object information retrieval.

**Example - Smart Teleporter**:
```
@set teleporter=DESCRIPTION:[strcat(
  A shimmering portal.,
  You sense it leads to [name([v(DESTINATION)])].,
  Currently located in [name([loc(%#)])]
)]
```

#### get/v
Attribute retrieval.

**Example - Stat Display**:
```
@set player=STATS:[strcat(
  HP: [v(HP)]/[v(MAX_HP)],
  MP: [v(MP)]/[v(MAX_MP)],
  Level: [v(LEVEL)]
)]
```

---

### LIST FUNCTIONS

#### words/first/rest/last
Basic list operations (space-separated).

**Example - Name Parser**:
```
@set parser=FIRST_NAME:[first([v(FULL_NAME)])]
@set parser=LAST_NAME:[last([v(FULL_NAME)])]
@set parser=MIDDLE:[rest([first([rest([v(FULL_NAME)])])])]
```

---

## Missing Functions (What Should Be Added)

### 🔥 Critical Missing Functions

Based on PennMUSH and MUSH best practices, here are the most important missing functions:

#### 1. List Iteration & Transformation (Critical!)
```
iter(list, code)           - Execute code for each element
filter(list, condition)    - Filter list by condition
map(list, function)        - Transform each element
fold(list, accumulator)    - Reduce list to single value
sort(list, [comparator])   - Sort list
```

**Why Critical**: Core to MUSH programming, enables complex softcode

#### 2. String Searching & Pattern Matching
```
member(element, list)      - Check if element in list
match(string, pattern)     - Wildcard matching
regmatch(string, regex)    - Regex matching
regedit(string, regex, replacement) - Regex replace
strmatch(string, pattern)  - Pattern matching
index(string, substring)   - Find substring position
```

**Why Critical**: Essential for parsing, validation, search

#### 3. Advanced String Manipulation
```
repeat(string, count)      - Repeat string N times
reverse(string)            - Reverse string
left(string, n)            - First N chars
right(string, n)           - Last N chars
mid(string, start, len)    - Better substr
center(string, width)      - Center with padding
ljust/rjust(string, width) - Left/right justify
edit(string, old, new)     - Find/replace
translate(string, from, to)- Character translation
```

**Why Critical**: Formatting, display, user experience

#### 4. Mathematical Extensions
```
abs(number)                - Absolute value
min(numbers...)            - Minimum value
max(numbers...)            - Maximum value
bound(val, min, max)       - Clamp value
ceil/floor/round(number)   - Rounding functions
sqrt(number)               - Square root
power(base, exp)           - Exponentiation
```

**Why Critical**: Game mechanics, calculations

#### 5. Database & Object Query
```
contents(object)           - List contents
lexits(room)               - List exits
children(object)           - Get children
lattr(object)              - List attributes
hasattr(obj, attr)         - Check attribute exists
search(type=VALUE)         - Search database
nearby(distance)           - Objects within distance
```

**Why Critical**: Essential for object interaction

#### 6. Time & Date
```
time()                     - Current timestamp
secs()                     - Seconds since epoch
convsecs(seconds)          - Convert to readable
timefmt(format, time)      - Format time
etimefmt(seconds)          - Elapsed time format
```

**Why Critical**: Events, scheduling, logs

#### 7. Formatting & Display
```
table(data, colsep, rowsep) - Format as table
columns(list, cols, colsep) - Multi-column layout
align(number, width)        - Align numbers with decimals
space(count)                - N spaces
ansi(color, text)           - Color codes
```

**Why Critical**: User experience, readability

---

## Comparison with PennMUSH

| Category | Web-Pennmush | PennMUSH | Gap |
|----------|--------------|----------|-----|
| String Functions | 6 | 60+ | 90% missing |
| List Functions | 4 | 40+ | 90% missing |
| Math Functions | 6 | 30+ | 80% missing |
| Logic Functions | 9 | 15 | 40% missing |
| Conditional Functions | 3 | 10 | 70% missing |
| Object Functions | 6 | 50+ | 88% missing |
| Database Functions | 0 | 30+ | 100% missing |
| Time Functions | 0 | 15+ | 100% missing |
| Permission Functions | 0 | 20+ | 100% missing |
| Formatting Functions | 0 | 25+ | 100% missing |
| **TOTAL** | **30** | **500+** | **94% missing** |

---

## Advanced Examples (Current Functions)

### Example 1: Dynamic HP Bar
```
@set player=HP:75
@set player=MAX_HP:100
@set player=HP_BAR:[strcat(
  HP: [v(HP)]/[v(MAX_HP)] [,
  [repeat(=, [div([mul([v(HP)], 20)], [v(MAX_HP)])])],
  [repeat(-, [sub(20, [div([mul([v(HP)], 20)], [v(MAX_HP)])])])]
)]
```
Currently broken - missing `repeat()` function!

### Example 2: Combat System
```
@set weapon=BASE_DAMAGE:20
@set weapon=CRIT_CHANCE:15

@set weapon=CALCULATE_DAMAGE:[ifelse(
  [lte([rand(100, 1)], [v(CRIT_CHANCE)])],
  [mul([v(BASE_DAMAGE)], 2)],
  [v(BASE_DAMAGE)]
)]
```
This works!

### Example 3: Quest Progress
```
@set quest=STEP1:1
@set quest=STEP2:1
@set quest=STEP3:0

@set quest=PROGRESS:[ifelse(
  [and([v(STEP1)], [v(STEP2)], [v(STEP3)])],
  Quest Complete!,
  [strcat(Progress: , [add([v(STEP1)], [v(STEP2)], [v(STEP3)])], /3)]
)]
```
This works!

### Example 4: Smart Door
```
@set door=LOCKED:1
@set door=KEY_HOLDER:#5

@set door=TRY_OPEN:[ifelse(
  [v(LOCKED)],
  [ifelse(
    [eq(%#, [v(KEY_HOLDER)])],
    Click! The door unlocks.,
    This door is locked.
  )],
  The door is already open.
)]
```
This works!

---

## Questions for You

Before I implement the expanded function library, I need clarification on desired functionality:

### 1. Function Priority
Which categories are most important for your use case?
- [ ] List iteration (iter, filter, map, fold)
- [ ] String pattern matching (regmatch, strmatch)
- [ ] Database queries (search, lsearch, contents)
- [ ] Time/date functions
- [ ] Formatting (table, columns)
- [ ] All of the above?

### 2. PennMUSH Compatibility
How strict should PennMUSH compatibility be?
- **Option A**: Exact PennMUSH function names and behavior
- **Option B**: Similar but improved (better names, modern syntax)
- **Option C**: Hybrid (core functions match, new functions use modern names)

### 3. Performance vs Features
- **Option A**: Implement all 500+ functions (huge library, slower startup)
- **Option B**: Implement top 100 critical functions (balanced)
- **Option C**: Implement on-demand (add functions as needed)

### 4. Advanced Features
Should softcode support:
- [ ] User-defined functions (@function command)
- [ ] Regex support (full regex engine)
- [ ] SQL queries (direct database access)
- [ ] External API calls (http(), fetch())
- [ ] File I/O (read/write text files)
- [ ] JSON parsing (json_parse, json_create)
- [ ] Encryption functions (sha256, encrypt, decrypt)

### 5. Security Boundaries
How permissive should softcode be?
- **Option A**: Sandboxed (safe, limited, no security risks)
- **Option B**: Moderate (most features, some restrictions)
- **Option C**: Full access (powerful but risky)

### 6. Softcode Execution Model
- **Option A**: Synchronous (simple, blocks on execution)
- **Option B**: Async (current, non-blocking, complex)
- **Option C**: Queued (execute in background, return later)

### 7. Error Handling
What should happen on errors?
- **Option A**: Silent fail (return empty string)
- **Option B**: Error messages (current: `#-1 ERROR`)
- **Option C**: Detailed debugging (show stack trace)

### 8. Documentation Format
How should softcode be documented?
- **Option A**: In-game help only
- **Option B**: Markdown reference guide (current)
- **Option C**: Interactive examples with web UI
- **Option D**: All of the above

---

## Recommendations

Based on MUSH best practices, I recommend implementing:

### Phase 1: Critical (Top 50 functions)
1. List iteration: `iter`, `filter`, `map`, `fold` (4)
2. String extensions: `repeat`, `left`, `right`, `mid`, `center` (5)
3. Math extensions: `abs`, `min`, `max`, `bound`, `sqrt`, `power` (6)
4. List operations: `extract`, `ldelete`, `linsert`, `lreplace`, `sort`, `member` (6)
5. Object queries: `contents`, `exits`, `lattr`, `hasattr`, `hasflag` (5)
6. String search: `match`, `strmatch`, `index`, `edit` (4)
7. Time functions: `time`, `secs`, `convsecs`, `timefmt` (4)
8. Formatting: `table`, `space`, `repeat`, `ljust`, `rjust` (5)
9. Database search: `search`, `lsearch` (2)
10. Advanced flow: `foreach`, `case`, `default` (3)
11. Misc utilities: `elements`, `grab`, `graball`, `lnum`, `munge` (5)

**Total Phase 1**: 50 functions (brings us to 80 total)

### Phase 2: Important (Next 50)
- Advanced list operations
- Regex support
- More object functions
- Permission checking
- User-defined functions

### Phase 3: Nice to Have (Final 50+)
- Trigonometry
- Advanced formatting
- External integrations
- File I/O

---

## Next Steps

Based on your answers, I can:

1. **Implement Critical Functions** (50 most important)
2. **Create Interactive Softcode Tutorial**
3. **Build Softcode Testing Interface** (web-based)
4. **Add User-Defined Functions** (@function command)
5. **Create Softcode Library** (pre-built useful code)
6. **Performance Optimization** (caching, compilation)

**What would you like me to focus on?**

Would you like me to:
- A) Implement the top 50 critical functions now?
- B) Focus on specific categories you need?
- C) Create comprehensive documentation first?
- D) Build all 500+ functions (will take time)?

Let me know your priorities and I'll build accordingly!

---

**Current Status**: 30 functions, basic but functional
**Potential**: 500+ functions, feature-complete MUSH scripting
**Your Input Needed**: Priorities and requirements

