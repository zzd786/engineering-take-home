import 'package:flutter/material.dart';

import 'api.dart';
import 'format.dart';
import 'models.dart';
import 'theme.dart';
import 'widgets.dart';

class ShareFormScreen extends StatefulWidget {
  const ShareFormScreen({
    super.key,
    required this.api,
    required this.doctors,
    required this.consent,
  });
  final ApiClient api;
  final List<Doctor> doctors;
  final SharingContext consent;

  @override
  State<ShareFormScreen> createState() => _ShareFormScreenState();
}

class _ShareFormScreenState extends State<ShareFormScreen> {
  int? _doctorId;
  late DateTime _to = widget.consent.today;
  late DateTime _from = DateTime(_to.year, _to.month, _to.day - 6);
  bool _notes = false;
  bool _review = false;
  bool _saving = false;
  bool _checking = false;
  String _period = 'Last 7 days';
  Future<SharingPreview?>? _preview;
  SharingPreview? _reviewPreview;
  String? _error;

  void _updatePreview() {
    _preview = _doctorId == null || _from.isAfter(_to) ? null : _loadPreview();
  }

  Future<SharingPreview?> _loadPreview() async {
    try {
      return await widget.api.previewShare(_doctorId!, _from, _to);
    } on Exception {
      return null;
    }
  }

  void _selectPeriod(String period) {
    setState(() {
      _period = period;
      if (period != 'Custom dates') {
        _to = widget.consent.today;
        final days = period == 'Today' ? 1 : (period == 'Last 7 days' ? 7 : 30);
        _from = DateTime(_to.year, _to.month, _to.day - days + 1);
      }
      _error = null;
      _updatePreview();
    });
  }

  Widget _summary(SharingPreview preview) => Container(
    margin: const EdgeInsets.symmetric(vertical: Space.m),
    padding: const EdgeInsets.all(Space.m),
    decoration: BoxDecoration(
      color: AppColors.surface,
      borderRadius: Radii.card,
      border: Border.all(color: AppColors.line),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Currently in this period', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: Space.s),
        Text('${preview.entries} diary ${preview.entries == 1 ? 'entry' : 'entries'}'),
        if (_notes)
          Text(
            '${preview.notes} ${preview.notes == 1 ? 'entry has' : 'entries have'} notes, which will be included.',
          ),
        if (!_notes) const Text('Your notes stay private under this choice.'),
        if (preview.entries == 0)
          const Text(
            'There are no diary entries in these dates. Choose different dates, or share this period for entries you add later.',
          ),
        const SizedBox(height: Space.s),
        const Text(
          'New entries dated within this period will also be shared until you stop sharing.',
        ),
        if (preview.overlaps > 0) ...[
          const SizedBox(height: Space.m),
          const Text(
            'You already share some of these dates with this doctor. This choice will not replace earlier sharing.',
          ),
          if (preview.overlapNotes && !_notes)
            const Text(
              'Earlier sharing already includes notes for some of these dates. Leaving notes off here does not make those notes private. Stop the earlier sharing to change that.',
            ),
        ],
      ],
    ),
  );

  Widget _previewPanel() => FutureBuilder<SharingPreview?>(
    future: _preview,
    builder: (context, snapshot) {
      if (_preview == null) {
        return const Text(
          'Choose a doctor and valid dates to see how many entries are in this period.',
        );
      }
      if (snapshot.connectionState != ConnectionState.done) {
        return const Padding(
          padding: EdgeInsets.all(Space.m),
          child: Text('Checking this period…'),
        );
      }
      if (snapshot.hasError || snapshot.data == null) {
        return TextButton(
          onPressed: () => setState(_updatePreview),
          child: const Text("Couldn't check this period. Try again."),
        );
      }
      return _summary(snapshot.data!);
    },
  );

  Doctor get _doctor => widget.doctors.firstWhere((doctor) => doctor.id == _doctorId);

  Future<void> _pickDate(bool start) async {
    final date = await showDatePicker(
      context: context,
      initialDate: start ? _from : _to,
      firstDate: DateTime(1900),
      lastDate: DateTime(2100),
    );
    if (date == null || !mounted) return;
    setState(() {
      if (start) {
        _from = date;
      } else {
        _to = date;
      }
      _period = 'Custom dates';
      _error = null;
      _updatePreview();
    });
  }

  Future<void> _reviewShare() async {
    if (_checking || _saving) return;
    if (_doctorId == null) {
      setState(() => _error = 'Choose your doctor first.');
      return;
    }
    if (_from.isAfter(_to)) {
      setState(() => _error = 'The end date must be on or after the start date.');
      return;
    }
    setState(() {
      _checking = true;
      _error = null;
    });
    try {
      final preview = await widget.api.previewShare(_doctorId!, _from, _to);
      if (mounted) {
        setState(() {
          _reviewPreview = preview;
          _review = true;
        });
      }
    } on Exception {
      if (mounted) setState(() => _error = "Couldn't check this period. Try again.");
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final share = await widget.api.createShare(_doctorId!, _from, _to, _notes);
      if (mounted) Navigator.of(context).pop(share);
    } on Exception {
      if (mounted) setState(() => _error = "Couldn't share your diary. Try again.");
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final dateStyle = OutlinedButton.styleFrom(
      minimumSize: const Size(48, 52),
      visualDensity: VisualDensity.standard,
      shape: const RoundedRectangleBorder(borderRadius: Radii.control),
    );
    return PopScope(
      canPop: !_saving && !_checking,
      child: Scaffold(
        appBar: AppBar(title: Text(_review ? 'Review diary sharing' : 'Share diary')),
        bottomNavigationBar: SafeArea(
          child: ContentColumn(
            child: Padding(
              padding: const EdgeInsets.all(Space.m),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Space.s),
                      child: Semantics(
                        liveRegion: true,
                        child: Text(
                          _error!,
                          style: text.bodyLarge?.copyWith(color: AppColors.error),
                        ),
                      ),
                    ),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(52),
                      visualDensity: VisualDensity.standard,
                    ),
                    onPressed: _saving || _checking ? null : (_review ? _save : _reviewShare),
                    child: Text(
                      _saving
                          ? 'Sharing…'
                          : (_checking
                                ? 'Checking…'
                                : (_review ? 'Confirm sharing' : 'Review sharing')),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        body: AbsorbPointer(
          absorbing: _saving || _checking,
          child: ListView(
            key: ValueKey(_review),
            padding: const EdgeInsets.all(Space.m),
            children: [
              ContentColumn(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      _review ? 'Check before sharing' : 'Choose what to share',
                      style: text.headlineMedium,
                    ),
                    const SizedBox(height: Space.l),
                    if (_review) ...[
                      Text(_doctor.name, style: text.titleMedium),
                      Text(_doctor.practice, style: text.bodyMedium),
                      _summary(_reviewPreview!),
                      const SizedBox(height: Space.m),
                      Container(
                        padding: const EdgeInsets.all(Space.m),
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          borderRadius: Radii.card,
                          border: Border.all(color: AppColors.line),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text('Your sharing choices', style: text.titleMedium),
                            for (final (index, point)
                                in widget.consent.points(_doctor, _from, _to, _notes).indexed)
                              Padding(
                                key: ValueKey('consent-point-$index'),
                                padding: const EdgeInsets.only(top: Space.m),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const ExcludeSemantics(child: Text('•  ')),
                                    Expanded(child: Text(point, style: text.bodyLarge)),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      ),
                      const SizedBox(height: Space.m),
                      Text(
                        'This choice only shares the selected dates. Your doctor can read this period until you stop sharing.',
                        style: text.bodyMedium,
                      ),
                      TextButton(
                        onPressed: _saving ? null : () => setState(() => _review = false),
                        style: TextButton.styleFrom(
                          minimumSize: const Size(48, 48),
                          visualDensity: VisualDensity.standard,
                        ),
                        child: const Text('Change doctor, dates or notes'),
                      ),
                    ] else ...[
                      DropdownButtonFormField<int>(
                        decoration: const InputDecoration(labelText: 'Your doctor'),
                        isExpanded: true,
                        initialValue: _doctorId,
                        items: [
                          for (final doctor in widget.doctors)
                            DropdownMenuItem(value: doctor.id, child: Text(doctor.name)),
                        ],
                        onChanged: (value) => setState(() {
                          _doctorId = value;
                          _error = null;
                          _updatePreview();
                        }),
                      ),
                      if (_doctorId != null)
                        Padding(
                          padding: const EdgeInsets.only(top: Space.s),
                          child: Text(_doctor.practice, style: text.bodyMedium),
                        ),
                      const SizedBox(height: Space.l),
                      Text('Dates to share', style: text.titleMedium),
                      const SizedBox(height: Space.s),
                      Text(
                        'Includes both dates and the days between. Dates use your diary timezone (${widget.consent.timezone}), which may differ from your device.',
                        style: text.bodyMedium,
                      ),
                      const SizedBox(height: Space.m),
                      Wrap(
                        spacing: Space.s,
                        runSpacing: Space.s,
                        children: [
                          for (final period in [
                            'Today',
                            'Last 7 days',
                            'Last 30 days',
                            'Custom dates',
                          ])
                            ChoiceChip(
                              label: Text(period),
                              selected: _period == period,
                              materialTapTargetSize: MaterialTapTargetSize.padded,
                              onSelected: (_) => _selectPeriod(period),
                            ),
                        ],
                      ),
                      const SizedBox(height: Space.m),
                      OutlinedButton(
                        onPressed: () => _pickDate(true),
                        style: dateStyle,
                        child: Text('From: ${formatCalendarDate(_from)}'),
                      ),
                      const SizedBox(height: Space.s),
                      OutlinedButton(
                        onPressed: () => _pickDate(false),
                        style: dateStyle,
                        child: Text('To: ${formatCalendarDate(_to)}'),
                      ),
                      const SizedBox(height: Space.l),
                      Text('What your doctor can read', style: text.titleMedium),
                      const SizedBox(height: Space.s),
                      const Text('Mood and symptoms are included.'),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Include my notes'),
                        subtitle: const Text('Your notes stay private unless you turn this on.'),
                        value: _notes,
                        onChanged: (value) => setState(() => _notes = value),
                      ),
                      _previewPanel(),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
