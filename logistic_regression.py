import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import KFold, train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest, f_classif, mutual_info_classif
import warnings
warnings.filterwarnings('ignore')

def main():
    # Load data
    df = pd.read_csv('products_cleaned.csv')
    
    print(f"Dataset shape: {df.shape}")
    print(f"Number of features: {df.shape[1] - 1}")
    
    # Drop currency as it's constant and not a feature
    if 'currency' in df.columns:
        df = df.drop(columns=['currency'])
    
    # Check for non-numeric columns
    non_numeric_cols = df.select_dtypes(exclude=[np.number]).columns
    if len(non_numeric_cols) > 0:
        print(f"\nNon-numeric columns found: {list(non_numeric_cols)}")
        print("Converting to numeric...")
        for col in non_numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Convert all columns to numeric, replacing errors with NaN
    df = df.apply(pd.to_numeric, errors='coerce')
    
    # Check missing values
    missing = df.isnull().sum()
    missing_pct = (missing / len(df)) * 100
    print(f"\nMissing values per column:")
    for col, pct in zip(missing.index, missing_pct):
        if pct > 0:
            print(f"  {col}: {missing[col]} values ({pct:.1f}%)")
    
    # Option 1: Remove columns with too many missing values
    high_missing = missing_pct[missing_pct > 30].index
    if len(high_missing) > 0:
        print(f"\nDropping columns with >30% missing: {list(high_missing)}")
        df = df.drop(columns=high_missing)
    
    # Fill remaining NaN with median
    df = df.fillna(df.median())
    
    # ANALYZE TARGET VARIABLE
    print("\n" + "="*50)
    print("TARGET VARIABLE ANALYSIS (price)")
    print("="*50)
    print(f"Price statistics:")
    print(f"  Mean: ${df['price'].mean():.2f}")
    print(f"  Median: ${df['price'].median():.2f}")
    print(f"  Std: ${df['price'].std():.2f}")
    print(f"  Min: ${df['price'].min():.2f}")
    print(f"  Max: ${df['price'].max():.2f}")
    
    # Visualize price distribution
    plt.figure(figsize=(12, 4))
    
    plt.subplot(1, 2, 1)
    plt.hist(df['price'], bins=30, edgecolor='black', alpha=0.7)
    plt.axvline(df['price'].median(), color='red', linestyle='--', label=f'Median: ${df["price"].median():.2f}')
    plt.axvline(df['price'].mean(), color='green', linestyle='--', label=f'Mean: ${df["price"].mean():.2f}')
    plt.xlabel('Price')
    plt.ylabel('Frequency')
    plt.title('Price Distribution')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Check if binary classification makes sense
    plt.subplot(1, 2, 2)
    median_price = df['price'].median()
    y_binary = (df['price'] > median_price).astype(int)
    class_counts = y_binary.value_counts()
    plt.bar(['Low Price', 'High Price'], class_counts.values, color=['blue', 'orange'])
    plt.title(f'Binary Classes (Split at ${median_price:.2f})')
    plt.ylabel('Count')
    for i, count in enumerate(class_counts.values):
        plt.text(i, count + 2, str(count), ha='center', fontweight='bold')
    plt.tight_layout()
    plt.savefig('price_analysis.png', dpi=100, bbox_inches='tight')
    plt.show()
    
    print(f"\nClass distribution:")
    print(f"  Low price (<=${median_price:.2f}): {class_counts.get(0, 0)} samples")
    print(f"  High price (>${median_price:.2f}): {class_counts.get(1, 0)} samples")
    print(f"  Ratio: {class_counts.get(1, 0)/len(df):.2%} high price")
    
    # Ask user if they want to proceed with binary classification
    proceed = input("\nProceed with binary classification? (yes/no): ").strip().lower()
    if proceed not in ['yes', 'y']:
        print("Analysis stopped by user.")
        return
    
    y = y_binary
    
    # Independent variables
    X = df.drop(columns=['price'])
    print(f"\nNumber of features before selection: {X.shape[1]}")
    
    # CRITICAL: FEATURE SELECTION FOR SMALL DATASET
    print("\n" + "="*50)
    print("FEATURE SELECTION (ESSENTIAL for 200 samples)")
    print("="*50)
    
    # Calculate number of features to keep (max 10% of samples or 20)
    max_features = min(20, len(df) // 10)  # 10:1 samples:features ratio
    print(f"Maximum features to keep: {max_features} (based on 10:1 samples:features ratio)")
    
    # Use ANOVA F-value for feature selection
    selector = SelectKBest(score_func=f_classif, k=max_features)
    X_selected = selector.fit_transform(X, y)
    selected_features = X.columns[selector.get_support()]
    feature_scores = selector.scores_[selector.get_support()]
    
    print(f"\nSelected {len(selected_features)} features:")
    feature_importance_df = pd.DataFrame({
        'Feature': selected_features,
        'F_Score': feature_scores
    }).sort_values('F_Score', ascending=False)
    
    print(feature_importance_df.head(10).to_string(index=False))
    
    # Update X with selected features
    X = pd.DataFrame(X_selected, columns=selected_features)
    feature_names = X.columns
    
    # Split data FIRST (before scaling) to avoid data leakage
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Scale features using training data only
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    X_train_scaled = pd.DataFrame(X_train_scaled, columns=feature_names)
    X_test_scaled = pd.DataFrame(X_test_scaled, columns=feature_names)
    
    # Initialize model with stronger regularization for small dataset
    # Use liblinear solver for L1 penalty (better for small datasets)
    model = LogisticRegression(
        penalty='l1',
        solver='liblinear',  # Better for small datasets
        C=0.1,  # Strong regularization (smaller C = stronger regularization)
        max_iter=1000,
        random_state=42,
        class_weight='balanced'  # Handle class imbalance
    )
    
    # K-Fold Cross Validation on training set only
    n_splits = 5
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    
    metrics = {
        'accuracy': [],
        'precision': [],
        'recall': [],
        'f1': [],
        'auc': []
    }
    
    coef_accumulator = np.zeros(X_train_scaled.shape[1])
    
    print(f"\n" + "="*50)
    print(f"RUNNING {n_splits}-FOLD CROSS VALIDATION")
    print("="*50)
    
    for fold, (train_idx, val_idx) in enumerate(kf.split(X_train_scaled), 1):
        X_fold_train, X_fold_val = X_train_scaled.iloc[train_idx], X_train_scaled.iloc[val_idx]
        y_fold_train, y_fold_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
        
        # Train model
        model.fit(X_fold_train, y_fold_train)
        
        # Predict
        y_pred = model.predict(X_fold_val)
        y_pred_proba = model.predict_proba(X_fold_val)[:, 1]
        
        # Calculate metrics
        metrics['accuracy'].append(accuracy_score(y_fold_val, y_pred))
        metrics['precision'].append(precision_score(y_fold_val, y_pred, zero_division=0))
        metrics['recall'].append(recall_score(y_fold_val, y_pred, zero_division=0))
        metrics['f1'].append(f1_score(y_fold_val, y_pred, zero_division=0))
        
        try:
            metrics['auc'].append(roc_auc_score(y_fold_val, y_pred_proba))
        except ValueError:
            metrics['auc'].append(0.5)  # Random chance
        
        # Accumulate coefficients
        coef_accumulator += np.abs(model.coef_[0])
        
        print(f"Fold {fold}: Accuracy = {metrics['accuracy'][-1]:.3f}, F1 = {metrics['f1'][-1]:.3f}")
    
    # Train final model on full training set
    print(f"\nTraining final model on full training set...")
    model.fit(X_train_scaled, y_train)
    
    # Test on holdout set
    y_test_pred = model.predict(X_test_scaled)
    y_test_proba = model.predict_proba(X_test_scaled)[:, 1]
    
    test_metrics = {
        'accuracy': accuracy_score(y_test, y_test_pred),
        'precision': precision_score(y_test, y_test_pred, zero_division=0),
        'recall': recall_score(y_test, y_test_pred, zero_division=0),
        'f1': f1_score(y_test, y_test_pred, zero_division=0),
        'auc': roc_auc_score(y_test, y_test_proba) if len(np.unique(y_test)) > 1 else 0.5
    }
    
    # Print Performance Matrix
    print("\n" + "="*50)
    print("CROSS-VALIDATION RESULTS")
    print("="*50)
    
    cv_means = {}
    cv_stds = {}
    
    for metric_name, values in metrics.items():
        if values:
            mean_val = np.mean(values)
            std_val = np.std(values)
            cv_means[metric_name] = mean_val
            cv_stds[metric_name] = std_val
            print(f"{metric_name.upper():<12} CV Mean: {mean_val:.4f} (+/- {std_val:.4f})")
    
    print("\n" + "="*50)
    print("TEST SET RESULTS (Holdout)")
    print("="*50)
    for metric_name, value in test_metrics.items():
        print(f"{metric_name.upper():<12}: {value:.4f}")
    
    # Feature Importance Analysis
    avg_coef = coef_accumulator / n_splits
    feature_importance = pd.DataFrame({
        'Feature': feature_names,
        'Importance (Abs Coef)': avg_coef
    }).sort_values('Importance (Abs Coef)', ascending=False)
    
    print("\n" + "="*50)
    print("TOP 10 FEATURES BY IMPORTANCE")
    print("="*50)
    print(feature_importance.head(10).to_string(index=False))
    
    # Plotting
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Performance metrics
    ax1 = axes[0, 0]
    metric_names = [m.upper() for m in cv_means.keys()]
    metric_values = list(cv_means.values())
    metric_stds = list(cv_stds.values())
    
    x_pos = np.arange(len(metric_names))
    bars = ax1.bar(x_pos, metric_values, yerr=metric_stds, capsize=5, 
                   color='skyblue', edgecolor='navy')
    ax1.set_ylabel('Score')
    ax1.set_title('Cross-Validation Performance')
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(metric_names, rotation=45)
    ax1.set_ylim(0, 1.1)
    
    for bar, val in zip(bars, metric_values):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 0.02,
                f'{val:.3f}', ha='center', va='bottom')
    
    # 2. Test vs CV comparison
    ax2 = axes[0, 1]
    test_values = [test_metrics[m] for m in cv_means.keys()]
    
    x = np.arange(len(metric_names))
    width = 0.35
    ax2.bar(x - width/2, metric_values, width, label='CV Mean', color='skyblue')
    ax2.bar(x + width/2, test_values, width, label='Test Set', color='salmon')
    ax2.set_ylabel('Score')
    ax2.set_title('CV Mean vs Test Set Performance')
    ax2.set_xticks(x)
    ax2.set_xticklabels(metric_names, rotation=45)
    ax2.legend()
    ax2.set_ylim(0, 1.1)
    
    # 3. Top 10 features
    ax3 = axes[1, 0]
    top_10 = feature_importance.head(10)
    ax3.barh(range(len(top_10)), top_10['Importance (Abs Coef)'].values)
    ax3.set_yticks(range(len(top_10)))
    ax3.set_yticklabels(top_10['Feature'])
    ax3.set_xlabel('Average Absolute Coefficient')
    ax3.set_title('Top 10 Feature Importances')
    ax3.invert_yaxis()  # Highest on top
    
    # 4. Confusion matrix
    ax4 = axes[1, 1]
    cm = confusion_matrix(y_test, y_test_pred)
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax4)
    ax4.set_xlabel('Predicted')
    ax4.set_ylabel('Actual')
    ax4.set_title('Confusion Matrix (Test Set)')
    
    plt.tight_layout()
    plt.savefig('logistic_regression_analysis.png', dpi=120, bbox_inches='tight')
    print("\nAnalysis complete. Results saved to 'logistic_regression_analysis.png'")
    
    # Save important features to CSV
    feature_importance.to_csv('feature_importance.csv', index=False)
    print("Feature importance saved to 'feature_importance.csv'")

if __name__ == "__main__":
    main()
