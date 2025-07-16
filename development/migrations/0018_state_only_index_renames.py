# State-only migration to satisfy Django's migration autodetector

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('development', '0017_rename_development_dock_sandbox_2aeba8_idx_development_sandbox_97b36e_idx_and_more'),
    ]

    operations = [
        # These are state-only operations to tell Django the indexes have been renamed
        # No actual database operations will be performed
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameIndex(
                    model_name='dockerportmapping',
                    new_name='development_sandbox_97b36e_idx',
                    old_name='development_dock_sandbox_2aeba8_idx',
                ),
                migrations.RenameIndex(
                    model_name='dockerportmapping',
                    new_name='development_contain_84368b_idx',
                    old_name='development_dock_contain_4d80c4_idx',
                ),
                migrations.RenameIndex(
                    model_name='dockerportmapping',
                    new_name='development_host_po_2071ac_idx',
                    old_name='development_dock_host_po_a9160d_idx',
                ),
                migrations.RenameIndex(
                    model_name='dockersandbox',
                    new_name='development_project_41ebb3_idx',
                    old_name='development_dock_project_3755a1_idx',
                ),
                migrations.RenameIndex(
                    model_name='dockersandbox',
                    new_name='development_convers_66f678_idx',
                    old_name='development_dock_convers_d45f8a_idx',
                ),
                migrations.RenameIndex(
                    model_name='dockersandbox',
                    new_name='development_contain_4ca3a0_idx',
                    old_name='development_dock_contain_2cb4be_idx',
                ),
                migrations.RenameIndex(
                    model_name='dockersandbox',
                    new_name='development_status_fe0828_idx',
                    old_name='development_dock_status_0a6455_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetespod',
                    new_name='development_project_34896b_idx',
                    old_name='development_kube_project_f5e7cd_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetespod',
                    new_name='development_convers_517a43_idx',
                    old_name='development_kube_convers_8587f7_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetespod',
                    new_name='development_pod_nam_3fae00_idx',
                    old_name='development_kube_pod_nam_214c1f_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetespod',
                    new_name='development_namespa_f5b94f_idx',
                    old_name='development_kube_namespa_283f9f_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetespod',
                    new_name='development_status_99da96_idx',
                    old_name='development_kube_status_0e403e_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetesportmapping',
                    new_name='development_pod_id_efaea1_idx',
                    old_name='development_kube_pod_id_2a1fa3_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetesportmapping',
                    new_name='development_contain_1dc930_idx',
                    old_name='development_kube_contain_5810c6_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetesportmapping',
                    new_name='development_service_b7742e_idx',
                    old_name='development_kube_service_1fb248_idx',
                ),
                migrations.RenameIndex(
                    model_name='kubernetesportmapping',
                    new_name='development_contain_3e335b_idx',
                    old_name='development_kube_contain_e10f86_idx',
                ),
            ],
            database_operations=[]
        ),
    ]