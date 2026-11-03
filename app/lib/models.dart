// Calendar dates are sent without UTC conversion: they name the patient's selected days.
String calendarDate(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';

// Supplies the doctor ID, name and practice used in recipient selection.
class Doctor {
  Doctor.fromJson(Map<String, dynamic> json)
    : id = json['id'] as int,
      name = json['name'] as String,
      practice = json['practice'] as String;
  final int id;
  final String name;
  final String practice;
}

// Builds confirmation wording from the server's consent template and patient timezone.
class SharingContext {
  SharingContext.fromJson(Map<String, dynamic> json)
    : today = DateTime.parse(json['today'] as String),
      timezone = json['timezone'] as String,
      version = json['consent_version'] as String,
      template = json['consent_template'] as String;
  final DateTime today;
  final String timezone;
  final String version;
  final String template;

  // Split before inserting the doctor's name so titles such as "Dr." stay intact.
  List<String> points(Doctor doctor, DateTime from, DateTime to, bool notes) => template
      .replaceAll('{notes}', notes ? 'Notes are included.' : 'My notes stay private.')
      .split(RegExp(r'(?<=\.) '))
      .map((point) => _fill(point, doctor, from, to, notes))
      .toList();

  String wording(Doctor doctor, DateTime from, DateTime to, bool notes) =>
      _fill(template, doctor, from, to, notes);

  String _fill(String text, Doctor doctor, DateTime from, DateTime to, bool notes) => text
      .replaceAll('{doctor}', doctor.name)
      .replaceAll('{from_date}', calendarDate(from))
      .replaceAll('{to_date}', calendarDate(to))
      .replaceAll('{timezone}', timezone)
      .replaceAll('{notes}', notes ? 'Notes are included.' : 'My notes stay private.');
}

// Counts the selected diary period and warns about existing permissions.
class SharingPreview {
  SharingPreview.fromJson(Map<String, dynamic> json)
    : entries = json['entry_count'] as int,
      notes = json['note_entry_count'] as int,
      overlaps = json['overlap_count'] as int,
      overlapNotes = json['overlap_includes_notes'] as bool;
  final int entries;
  final int notes;
  final int overlaps;
  final bool overlapNotes;
}

// Holds the public share details and revocation status shown to the patient.
class DiaryShare {
  DiaryShare.fromJson(Map<String, dynamic> json)
    : id = json['id'] as int,
      doctorId = json['clinician_id'] as int,
      from = json['from_date'] as String,
      to = json['to_date'] as String,
      includeNotes = json['include_notes'] as bool,
      revoked = json['revoked_at'] != null;
  final int id;
  final int doctorId;
  final String from;
  final String to;
  final bool includeNotes;
  final bool revoked;
}

// Shows which doctor read the diary, when, and how many entries were returned.
class DiaryRead {
  DiaryRead.fromJson(Map<String, dynamic> json)
    : doctorName = json['clinician_name'] as String,
      accessedAt = DateTime.parse(json['accessed_at'] as String),
      entryIds = List<int>.from(json['entry_ids'] as List);
  final String doctorName;
  final DateTime accessedAt;
  final List<int> entryIds;
}

class DiaryEntry {
  const DiaryEntry({
    this.id,
    required this.recordedAt,
    required this.mood,
    this.symptoms = const [],
    this.note,
  });

  final int? id;
  final DateTime recordedAt;
  final int mood;
  final List<String> symptoms;
  final String? note;

  factory DiaryEntry.fromJson(Map<String, dynamic> json) => DiaryEntry(
    id: json['id'] as int,
    recordedAt: DateTime.parse(json['recorded_at'] as String),
    mood: json['mood'] as int,
    symptoms: List<String>.from(json['symptoms'] as List),
    note: json['note'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'recorded_at': recordedAt.toUtc().toIso8601String(),
    'mood': mood,
    'symptoms': symptoms,
    'note': note,
  };
}
