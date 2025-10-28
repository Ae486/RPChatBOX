import 'package:flutter/material.dart';
import '../widgets/optimized_latex_renderer.dart';
import '../test/latex_test_examples.dart';

/// LaTeX渲染测试页面
/// 用于测试和验证优化后的LaTeX渲染器
class LaTeXTestPage extends StatefulWidget {
  const LaTeXTestPage({super.key});

  @override
  State<LaTeXTestPage> createState() => _LaTeXTestPageState();
}

class _LaTeXTestPageState extends State<LaTeXTestPage> with TickerProviderStateMixin {
  late TabController _tabController;
  final Map<String, List<String>> _testCases = LaTeXTestExamples.getCategorizedTestCases();
  final Map<String, String> _expectedResults = LaTeXTestExamples.getExpectedResults();

  bool _showRawLaTeX = false;
  String _selectedCategory = 'Basic';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(
      length: _testCases.keys.length,
      vsync: this,
    );
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('LaTeX渲染测试'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: _testCases.keys.map((category) {
            return Tab(text: category);
          }).toList(),
          onTap: (index) {
            setState(() {
              _selectedCategory = _testCases.keys.elementAt(index);
            });
          },
        ),
        actions: [
          IconButton(
            icon: Icon(_showRawLaTeX ? Icons.code : Icons.preview),
            onPressed: () {
              setState(() {
                _showRawLaTeX = !_showRawLaTeX;
              });
            },
            tooltip: _showRawLaTeX ? '显示渲染结果' : '显示原始LaTeX',
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              setState(() {});
            },
            tooltip: '刷新',
          ),
        ],
      ),
      body: TabBarView(
        controller: _tabController,
        children: _testCases.keys.map((category) {
          return _buildCategoryTest(category);
        }).toList(),
      ),
    );
  }

  Widget _buildCategoryTest(String category) {
    final testCases = _testCases[category]!;
    final expectedResult = _expectedResults[category]!;

    return Column(
      children: [
        // 预期结果提示
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          color: Theme.of(context).colorScheme.primaryContainer,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                category,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                expectedResult,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onPrimaryContainer,
                ),
              ),
            ],
          ),
        ),

        // 测试用例列表
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: testCases.length,
            itemBuilder: (context, index) {
              final testCase = testCases[index];
              return _buildTestCaseItem(testCase, index);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildTestCaseItem(String testCase, int index) {
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 测试用例标题
            Row(
              children: [
                Text(
                  '测试用例 ${index + 1}',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.copy),
                  onPressed: () {
                    // 这里可以添加复制功能
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('已复制到剪贴板')),
                    );
                  },
                  visualDensity: VisualDensity.compact,
                  tooltip: '复制LaTeX代码',
                ),
              ],
            ),
            const SizedBox(height: 8),

            // 原始LaTeX代码或渲染结果
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: Theme.of(context).colorScheme.outline,
                ),
              ),
              child: _showRawLaTeX
                  ? _buildRawLaTeXView(testCase)
                  : _buildRenderedView(testCase),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRawLaTeXView(String testCase) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SelectableText(
        testCase,
        style: TextStyle(
          fontFamily: 'monospace',
          fontSize: 14,
          color: Theme.of(context).colorScheme.onSurface,
        ),
      ),
    );
  }

  Widget _buildRenderedView(String testCase) {
    return OptimizedLaTeXRenderer(
      content: testCase,
      textStyle: TextStyle(
        fontSize: 16,
        color: Theme.of(context).colorScheme.onSurface,
      ),
      preferNative: true,
    );
  }
}