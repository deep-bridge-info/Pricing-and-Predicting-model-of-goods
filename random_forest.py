import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import KFold, train_test_split, GridSearchCV
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Lasso
from sklearn.feature_selection import SelectFromModel
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import warnings
import joblib

warnings.filterwarnings('ignore')

def adjusted_r2(r2, n, p):
    """Calculate Adjusted R-squared"""
    if n - p - 1 <= 0:
        return r2
    return 1 - (1 - r2) * (n - 1) / (n - p - 1)

def main():
    # Load data
    df = pd.read_csv('products_cleaned.csv')
    
    # Drop currency as it's constant and not a feature
    if 'currency' in df.columns:
        df = df.drop(columns=['currency'])
        
    # Convert all columns to numeric, replacing errors with NaN
    df = df.apply(pd.to_numeric, errors='coerce')
    
    # Fill NaN values with median, and any remaining with 0 (e.g. if column was all NaN)
    df = df.fillna(df.median()).fillna(0)
    
    # Target variable (Regression on price)
    y = df['price']
    y_log = np.log1p(y)  # Apply log transformation
    X = df.drop(columns=['price'])
    
    # Split into train/test sets (80/20)
    X_train_full, X_test, y_train_full_log, y_test_log = train_test_split(X, y_log, test_size=0.2, random_state=42)
    y_test_orig = np.expm1(y_test_log)
    
    # ==========================================
    # Tree-Based Feature Selection
    # ==========================================
    print("Applying Tree-Based Feature Selection...")
    # Using a preliminary Random Forest to select features instead of Lasso, 
    # because Lasso is linear and might drop features with non-linear relationships.
    selector_rf = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=-1)
    tree_selector = SelectFromModel(selector_rf, threshold='median')
    tree_selector.fit(X_train_full, y_train_full_log)
    
    selected_features = X.columns[(tree_selector.get_support())]
    if len(selected_features) == 0:
        print("Feature selection dropped all features. Falling back to all features.")
        selected_features = X.columns
    else:
        print(f"Tree-Based Selection kept {len(selected_features)} features out of {len(X.columns)}")
        
    X_train_sel = X_train_full[selected_features]
    X_test_sel = X_test[selected_features]
    
    # Initialize Random Forest Regressor base model
    rf_base = RandomForestRegressor(random_state=42)
    
    # ==========================================
    # Grid Search with 5-Fold Cross Validation
    # ==========================================
    print("\nRunning Grid Search with 5-Fold Cross Validation...")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    
    param_grid = {
        'n_estimators': [50, 100, 200],
        'max_depth': [None, 10, 20],
        'min_samples_split': [2, 5],
        'min_samples_leaf': [1, 2],
        'max_features': ['sqrt', 'log2', None]
    }
    
    grid_search = GridSearchCV(
        estimator=rf_base, 
        param_grid=param_grid, 
        cv=kf, 
        scoring='r2', 
        n_jobs=-1, 
        verbose=1
    )
    
    grid_search.fit(X_train_sel, y_train_full_log)
    best_rf = grid_search.best_estimator_
    
    print(f"\nBest Parameters found: {grid_search.best_params_}")
    
    # Optional: Re-run 5-fold CV with best_rf to get all 4 performance dimensions
    cv_metrics = {
        'r2': [],
        'adj_r2': [],
        'mae': [],
        'rmse': []
    }
    
    n_features = X_train_sel.shape[1]
    
    for train_idx, val_idx in kf.split(X_train_sel):
        X_fold_train, X_fold_val = X_train_sel.iloc[train_idx], X_train_sel.iloc[val_idx]
        y_fold_train_log, y_fold_val_log = y_train_full_log.iloc[train_idx], y_train_full_log.iloc[val_idx]
        y_fold_val_orig = np.expm1(y_fold_val_log)
        
        best_rf.fit(X_fold_train, y_fold_train_log)
        y_pred_log = best_rf.predict(X_fold_val)
        y_pred_orig = np.expm1(y_pred_log)
        
        r2 = r2_score(y_fold_val_orig, y_pred_orig)
        adj_r2 = adjusted_r2(r2, len(y_fold_val_orig), n_features)
        mae = mean_absolute_error(y_fold_val_orig, y_pred_orig)
        rmse = np.sqrt(mean_squared_error(y_fold_val_orig, y_pred_orig))
        
        cv_metrics['r2'].append(r2)
        cv_metrics['adj_r2'].append(adj_r2)
        cv_metrics['mae'].append(mae)
        cv_metrics['rmse'].append(rmse)
        
    print("\n" + "="*40)
    print("BEST MODEL CROSS VALIDATION PERFORMANCE (5 Folds)")
    print("="*40)
    for metric in cv_metrics:
        print(f"{metric.upper():<10}: {np.mean(cv_metrics[metric]):.4f} (+/- {np.std(cv_metrics[metric]):.4f})")
        
    # ==========================================
    # Test Set Evaluation with Best Model
    # ==========================================
    best_rf.fit(X_train_sel, y_train_full_log)
    y_test_pred_log = best_rf.predict(X_test_sel)
    y_test_pred_orig = np.expm1(y_test_pred_log)
    
    test_r2 = r2_score(y_test_orig, y_test_pred_orig)
    test_adj_r2 = adjusted_r2(test_r2, len(y_test_orig), n_features)
    test_mae = mean_absolute_error(y_test_orig, y_test_pred_orig)
    test_rmse = np.sqrt(mean_squared_error(y_test_orig, y_test_pred_orig))
    
    print("\n" + "="*40)
    print("TEST SET PERFORMANCE")
    print("="*40)
    print(f"R2        : {test_r2:.4f}")
    print(f"ADJ_R2    : {test_adj_r2:.4f}")
    print(f"MAE       : {test_mae:.4f}")
    print(f"RMSE      : {test_rmse:.4f}")
    
    # ==========================================
    # Feature Ranking
    # ==========================================
    importances = best_rf.feature_importances_
    feature_importance = pd.DataFrame({
        'Feature': selected_features,
        'Importance': importances
    }).sort_values(by='Importance', ascending=False)
    
    print("\n" + "="*40)
    print("FEATURE RANKING (Top 10)")
    print("="*40)
    print(feature_importance.head(10).to_string(index=False))
    
    # Plotting Feature Importances
    plt.figure(figsize=(10, 6))
    top_features = feature_importance.head(15)
    sns.barplot(x='Importance', y='Feature', data=top_features, palette='viridis', hue='Feature', legend=False)
    plt.title('Top 15 Feature Importances (Best Tuned Random Forest)')
    plt.xlabel('Gini Importance')
    plt.ylabel('Feature')
    plt.tight_layout()
    
    plot_filename = 'rf_feature_importance.png'
    plt.savefig(plot_filename)
    print(f"\nFeature ranking graph saved to '{plot_filename}'")
    
    # Save the trained model, feature names, and medians for future prediction
    joblib.dump(best_rf, 'best_rf_model.pkl')
    joblib.dump(selected_features, 'rf_features.pkl')
    joblib.dump(X_train_full.median(), 'rf_medians.pkl')
    print("Model, features, and medians saved for sensitivity prediction!")
    
if __name__ == "__main__":
    main()