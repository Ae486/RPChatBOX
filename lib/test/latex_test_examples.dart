/// LaTeX测试用例
/// 用于验证优化后的LaTeX渲染器支持的各种公式格式
class LaTeXTestExamples {
  /// 基础数学公式测试用例
  static const List<String> basicFormulas = [
    // 简单分数
    r'The formula is $\frac{1}{2}$.',
    r'Mixed: $x = \frac{a + b}{c - d}$.',

    // 根号
    r'Square root: $\sqrt{16} = 4$.',
    r'Complex root: $\sqrt{x^2 + y^2}$.',
    r'Nth root: $\sqrt[n]{a}$.',

    // 上下标
    r'Power: $x^2 + y^3 = z$.',
    r'Subscript: $a_1 + a_2 = a_{12}$.',
    r'Combined: $x_i^2$.',

    // 希腊字母
    r'Greek: $\alpha, \beta, \gamma, \delta$.',
    r'Upper case: $\Gamma, \Delta, \Theta, \Lambda$.',

    // 三角函数
    r'Trigonometric: $\sin(x) + \cos(y) = 1$.',
    r'Inverse: $\arcsin(x) + \arccos(y) = \frac{\pi}{2}$.',
  ];

  /// 高级数学公式测试用例
  static const List<String> advancedFormulas = [
    // 求和
    r'Summation: $\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$.',
    r'Complex sum: $\sum_{i=0}^{\infty} \frac{x^i}{i!} = e^x$.',

    // 积分
    r'Integral: $\int_{a}^{b} f(x) dx$.',
    r'Definite integral: $\int_{0}^{\pi} \sin(x) dx = 2$.',
    r'Improper integral: $\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}$.',

    // 极限
    r'Limit: $\lim_{x \to \infty} \frac{1}{x} = 0$.',
    r'Derivative: $\lim_{h \to 0} \frac{f(x+h) - f(x)}{h}$.',

    // 乘积
    r'Product: $\prod_{i=1}^{n} i = n!$.',
    r'Gamma function: $\Gamma(z) = \int_{0}^{\infty} t^{z-1} e^{-t} dt$.',

    // 微分
    r'Partial derivative: $\frac{\partial f}{\partial x}$.',
    r'Gradient: $\nabla f = \left(\frac{\partial f}{\partial x}, \frac{\partial f}{\partial y}\right)$.',
    r'Laplacian: $\nabla^2 f = \frac{\partial^2 f}{\partial x^2} + \frac{\partial^2 f}{\partial y^2}$.',
  ];

  /// 集合论和逻辑测试用例
  static const List<String> setLogicFormulas = [
    // 集合符号
    r'Set notation: $x \in A$ and $x \notin B$.',
    r'Subset: $A \subset B$ and $C \subseteq D$.',
    r'Union and intersection: $A \cup B$ and $A \cap B$.',
    r'Empty set: $\emptyset$ or $\varnothing$.',

    // 逻辑符号
    r'Quantifiers: $\forall x \in A, \exists y \in B$ such that $x < y$.',
    r'Negation: $\neg P$ or $\lnot P$.',
    r'Implication: $P \implies Q$.',

    // 等价关系
    r'Equivalence: $A \equiv B$.',
    r'Approximation: $x \approx y$.',
    r'Similarity: $A \sim B$.',
  ];

  /// 矩阵和线性代数测试用例
  static const List<String> matrixFormulas = [
    // 简单矩阵（可能会降级到WebView）
    r'Matrix: $\begin{pmatrix} a & b \\ c & d \end{pmatrix}$.',
    r'Determinant: $\det\begin{pmatrix} a & b \\ c & d \end{pmatrix} = ad - bc$.',
    r'Transpose: $A^T$.',

    // 向量
    r'Vector: $\vec{v} = (v_1, v_2, v_3)$.',
    r'Dot product: $\vec{a} \cdot \vec{b} = |\vec{a}||\vec{b}|\cos\theta$.',
    r'Cross product: $\vec{a} \times \vec{b}$.',
  ];

  /// 物理学公式测试用例
  static const List<String> physicsFormulas = [
    // 经典力学
    r'Newton\'s second law: $F = ma$.',
    r'Kinetic energy: $E_k = \frac{1}{2}mv^2$.',
    r'Momentum: $p = mv$.',

    // 电磁学
    r'Coulomb\'s law: $F = k\frac{q_1 q_2}{r^2}$.',
    r'Maxwell\'s equations: $\nabla \cdot \vec{E} = \frac{\rho}{\varepsilon_0}$.',

    // 量子力学
    r'Schrödinger equation: $i\hbar\frac{\partial\psi}{\partial t} = \hat{H}\psi$.',
    r'Planck\'s relation: $E = h\nu$.',
    r'Uncertainty principle: $\Delta x \Delta p \geq \frac{\hbar}{2}$.',
  ];

  /// 复杂公式测试用例（这些可能需要WebView渲染）
  static const List<String> complexFormulas = [
    // 多行公式
    r'''
$$
f(x) = \begin{cases}
x^2 & \text{if } x \geq 0 \\
-x^2 & \text{if } x < 0
\end{cases}
$$
''',

    // 分段函数
    r'''
$$
|x| = \begin{cases}
x & \text{if } x \geq 0 \\
-x & \text{if } x < 0
\end{cases}
$$
''',

    // 级数展开
    r'Taylor series: $e^x = \sum_{n=0}^{\infty} \frac{x^n}{n!} = 1 + x + \frac{x^2}{2!} + \frac{x^3}{3!} + \cdots$',

    // 傅里叶级数
    r'Fourier series: $f(x) = \frac{a_0}{2} + \sum_{n=1}^{\infty} \left(a_n\cos\frac{n\pi x}{L} + b_n\sin\frac{n\pi x}{L}\right)$',
  ];

  /// 所有测试用例
  static List<String> getAllTestCases() {
    return [
      ...basicFormulas,
      ...advancedFormulas,
      ...setLogicFormulas,
      ...matrixFormulas,
      ...physicsFormulas,
      ...complexFormulas,
    ];
  }

  /// 按难度分类的测试用例
  static Map<String, List<String>> getCategorizedTestCases() {
    return {
      'Basic': basicFormulas,
      'Advanced': advancedFormulas,
      'Set Theory & Logic': setLogicFormulas,
      'Matrices & Vectors': matrixFormulas,
      'Physics': physicsFormulas,
      'Complex (WebView)': complexFormulas,
    };
  }

  /// 预期渲染结果的描述
  static Map<String, String> getExpectedResults() {
    return {
      'Basic': 'Should render correctly with flutter_math_fork',
      'Advanced': 'Should render correctly with flutter_math_fork',
      'Set Theory & Logic': 'Should render correctly with flutter_math_fork',
      'Matrices & Vectors': 'May fall back to WebView for complex matrices',
      'Physics': 'Should render correctly with flutter_math_fork',
      'Complex (WebView)': 'Will fall back to WebView rendering',
    };
  }
}