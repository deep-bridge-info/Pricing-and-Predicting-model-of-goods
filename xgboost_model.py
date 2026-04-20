import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import KFold, train_test_split, GridSearchCV
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import SelectFromModel
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
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
    df = pd.read_csv('products_cleaned_xgb.csv')
    
    # Drop currency as it's constant and not a feature
    if 'currency' in df.columns:
        df = df.drop(columns=['currency'])

    # Convert all columns to numeric, replacing errors with NaN
    df = df.apply(pd.to_numeric, errors='coerce')
    
    # Target variable (Regression on price)
    y = df['price']
    X = df.drop(columns=['price'])
    
    # Split into train/test sets (80/20)
    X_train_full, X_test, y_train_full, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Calculate medians on training data for future prediction filling
    # But DO NOT fillna on the training data itself, let XGBoost handle NaNs
    train_medians = X_train_full.median()
    
    # ==========================================
    # Tree-Based Feature Selection
    # ==========================================
    print("Applying Tree-Based Feature Selection (Random Forest)...")
    # Using RandomForest to select features to prevent overfitting that might occur 
    # if we use XGBoost for both selection and final modeling (data leakage).
    # Note: RF cannot handle NaNs, so we temporarily fill them just for selection
    X_train_sel_temp = X_train_full.fillna(train_medians).fillna(0)
    selector_rf = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=-1)
    tree_selector = SelectFromModel(selector_rf, threshold='median')
    tree_selector.fit(X_train_sel_temp, y_train_full)
    
    selected_features = X.columns[(tree_selector.get_support())]
    if len(selected_features) == 0:
        print("Feature selection dropped all features. Falling back to all features.")
        selected_features = X.columns
    else:
        print(f"Tree-Based Selection kept {len(selected_features)} features out of {len(X.columns)}")
        
    X_train_sel = X_train_full[selected_features]
    X_test_sel = X_test[selected_features]
    
    # Initialize XGBoost Regressor base model
    # Using squaredlogerror so we can train on original scale while still penalizing relative errors
    xgb_base = xgb.XGBRegressor(random_state=42, objective='reg:squaredlogerror')
    
    # ==========================================
    # Grid Search with 5-Fold Cross Validation
    # ==========================================
    print("\nRunning Grid Search with 5-Fold Cross Validation...")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    
    param_grid = {
        'n_estimators': [100, 200],
        'max_depth': [3, 6, 10],
        'learning_rate': [0.01, 0.1, 0.2],
        'subsample': [0.8, 1.0],
        'colsample_bytree': [0.8, 1.0]
    }
    
    grid_search = GridSearchCV(
        estimator=xgb_base, 
        param_grid=param_grid, 
        cv=kf, 
        scoring='r2', 
        n_jobs=-1, 
        verbose=1
    )
    
    grid_search.fit(X_train_sel, y_train_full)
    best_xgb = grid_search.best_estimator_
    
    print(f"\nBest Parameters found: {grid_search.best_params_}")
    
    # Optional: Re-run 5-fold CV with best_xgb to get all 4 performance dimensions
    cv_metrics = {
        'r2': [],
        'adj_r2': [],
        'mae': [],
        'rmse': []
    }
    
    n_features = X_train_sel.shape[1]
    
    for train_idx, val_idx in kf.split(X_train_sel):
        X_fold_train, X_fold_val = X_train_sel.iloc[train_idx], X_train_sel.iloc[val_idx]
        y_fold_train, y_fold_val = y_train_full.iloc[train_idx], y_train_full.iloc[val_idx]
        
        best_xgb.fit(X_fold_train, y_fold_train)
        y_pred = best_xgb.predict(X_fold_val)
        
        r2 = r2_score(y_fold_val, y_pred)
        adj_r2 = adjusted_r2(r2, len(y_fold_val), n_features)
        mae = mean_absolute_error(y_fold_val, y_pred)
        rmse = np.sqrt(mean_squared_error(y_fold_val, y_pred))
        
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
    best_xgb.fit(X_train_sel, y_train_full)
    y_test_pred = best_xgb.predict(X_test_sel)
    
    test_r2 = r2_score(y_test, y_test_pred)
    test_adj_r2 = adjusted_r2(test_r2, len(y_test), n_features)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))
    
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
    importances = best_xgb.feature_importances_
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
    plt.title('Top 15 Feature Importances (Best Tuned XGBoost)')
    plt.xlabel('F-Score / Gain Importance')
    plt.ylabel('Feature')
    plt.tight_layout()
    
    plot_filename = 'xgb_feature_importance.png'
    plt.savefig(plot_filename)
    print(f"\nFeature ranking graph saved to '{plot_filename}'")
    
    # Save the trained model, feature names, and medians for future prediction
    joblib.dump(best_xgb, 'best_xgb_model.pkl')
    joblib.dump(selected_features, 'xgb_features.pkl')
    joblib.dump(train_medians, 'xgb_medians.pkl')
    print("Model, features, and medians saved for sensitivity prediction!")
    
if __name__ == "__main__":
    main()
