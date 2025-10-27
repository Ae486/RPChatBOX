/// 自定义角色模型
class CustomRole {
  final String id;
  String name;
  String description;
  String systemPrompt;
  String icon;

  CustomRole({
    required this.id,
    required this.name,
    required this.description,
    required this.systemPrompt,
    this.icon = '✨',
  });

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'description': description,
      'systemPrompt': systemPrompt,
      'icon': icon,
    };
  }

  factory CustomRole.fromJson(Map<String, dynamic> json) {
    return CustomRole(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String,
      systemPrompt: json['systemPrompt'] as String,
      icon: json['icon'] as String? ?? '✨',
    );
  }
}



