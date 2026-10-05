/**
 * Tiny safe arithmetic evaluator for the command palette search.
 *
 * Supports: + - * / % , ^ / ** (power, right-associative), unary +/-,
 * parentheses and decimal numbers. Anything it does not fully understand
 * yields `null` - there is no `eval`, no access to globals.
 */

type Token =
    | { type: 'num'; value: number }
    | { type: 'op'; value: '+' | '-' | '*' | '/' | '%' | '^' }
    | { type: 'lparen' }
    | { type: 'rparen' }

// Only the left-associative binary operators; `^` is parsed separately so that
// unary minus binds looser than it (`-2^2` === `-(2^2)`, the math convention).
const PRECEDENCE: Record<string, number> = { '+': 1, '-': 1, '*': 2, '/': 2, '%': 2 }

function tokenize(src: string): Token[] | null {
    const tokens: Token[] = []
    let i = 0
    while (i < src.length) {
        const c = src[i]
        if (c === ' ' || c === '\t') {
            i++
            continue
        }
        if ((c >= '0' && c <= '9') || c === '.') {
            let j = i
            let dots = 0
            while (j < src.length && ((src[j] >= '0' && src[j] <= '9') || src[j] === '.')) {
                if (src[j] === '.') dots++
                j++
            }
            if (dots > 1) return null
            const value = Number(src.slice(i, j))
            if (!Number.isFinite(value)) return null
            tokens.push({ type: 'num', value })
            i = j
            continue
        }
        if (c === '*' && src[i + 1] === '*') {
            tokens.push({ type: 'op', value: '^' })
            i += 2
            continue
        }
        if (c === '+' || c === '-' || c === '*' || c === '/' || c === '%' || c === '^') {
            tokens.push({ type: 'op', value: c })
            i++
            continue
        }
        if (c === '(') {
            tokens.push({ type: 'lparen' })
            i++
            continue
        }
        if (c === ')') {
            tokens.push({ type: 'rparen' })
            i++
            continue
        }
        return null
    }
    return tokens
}

function apply(op: string, a: number, b: number): number {
    switch (op) {
        case '+': return a + b
        case '-': return a - b
        case '*': return a * b
        case '/': return a / b
        case '%': return a % b
        case '^': return a ** b
        default: throw new Error('bad operator')
    }
}

/**
 * Evaluate `input` as an arithmetic expression.
 * Returns the finite numeric result, or `null` if the input is not a
 * complete, well-formed expression that contains at least one operator.
 */
export function tryCalc(input: string): number | null {
    const src = input.trim()
    if (!src) return null
    // Cheap gate: a bare number or a plain search term is not a calculation.
    if (!/[+\-*/%^]/.test(src.slice(1)) && !src.includes('**')) return null

    const tokens = tokenize(src)
    if (!tokens || tokens.length === 0) return null

    let pos = 0
    let usedBinaryOp = false
    const peek = () => tokens[pos]

    function parsePrimary(): number {
        const tk = peek()
        if (!tk) throw new Error('unexpected end')
        if (tk.type === 'num') {
            pos++
            return tk.value
        }
        if (tk.type === 'lparen') {
            pos++
            const value = parseExpr(0)
            const close = peek()
            if (!close || close.type !== 'rparen') throw new Error('missing )')
            pos++
            return value
        }
        throw new Error('unexpected token')
    }

    function parseUnary(): number {
        const tk = peek()
        if (tk && tk.type === 'op' && (tk.value === '+' || tk.value === '-')) {
            pos++
            const value = parseUnary()
            return tk.value === '-' ? -value : value
        }
        return parsePower()
    }

    function parsePower(): number {
        const base = parsePrimary()
        const tk = peek()
        if (tk && tk.type === 'op' && tk.value === '^') {
            pos++
            const exponent = parseUnary() // right-associative, allows `2^-3`
            usedBinaryOp = true
            return base ** exponent
        }
        return base
    }

    function parseExpr(minPrec: number): number {
        let left = parseUnary()
        for (;;) {
            const tk = peek()
            if (!tk || tk.type !== 'op') break
            const prec = PRECEDENCE[tk.value]
            if (prec === undefined || prec < minPrec) break
            pos++
            const rightAssoc = tk.value === '^'
            const right = parseExpr(rightAssoc ? prec : prec + 1)
            left = apply(tk.value, left, right)
            usedBinaryOp = true
        }
        return left
    }

    try {
        const result = parseExpr(0)
        if (pos !== tokens.length) return null
        if (!usedBinaryOp) return null
        if (!Number.isFinite(result)) return null
        return result
    } catch {
        return null
    }
}

/** Render a calc result without binary floating-point noise. */
export function formatCalcResult(n: number): string {
    if (Object.is(n, -0)) return '0'
    if (Number.isInteger(n) && Math.abs(n) < 1e15) return String(n)
    return String(Number(n.toPrecision(10)))
}
